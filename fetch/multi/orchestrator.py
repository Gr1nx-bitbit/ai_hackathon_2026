"""
Orchestrator Agent — coordinates the multi-stage pipeline across specialist agents.

Message flow:
    client → orchestrator → Stage1Agent
                          ← Stage1Response
                          → Stage2Agent
                          ← Stage2Response
                          → [Stage3TcrAgent, Stage3BcellAgent]  (parallel)
                          ← Stage3TcrResponse
                          ← Stage3BcellResponse  (join when both arrive)
                          → Stage4Agent
                          ← Stage4Response
                          → ReportAgent
                          ← ReportResponse
                          → client

The orchestrator is the only agent the client interacts with. It replicates
the routing logic from src/agents/nodes.py without the LangGraph state machine:
  - Stage1 retry loop (low pLDDT → fallback mode)
  - Stage2 early exit gate
  - Stage3 parallel fan-out and join barrier (tcr_done + bcell_done flags)
  - Stage3 high-risk early exit
  - Timeout cleanup via on_interval (120 s per session)

Usage:
    from fetch.multi.orchestrator import create_orchestrator
    orch = create_orchestrator(stage1_addr, stage2_addr, ...)
"""

import asyncio
import json
import os
import time
import uuid
from typing import Optional

try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from uagents import Agent, Context

from fetch.messages import PipelineRequest, PipelineResponse
from fetch.multi.messages import (
    Stage1Request, Stage1Response,
    Stage2Request, Stage2Response,
    Stage3TcrRequest, Stage3TcrResponse,
    Stage3BcellRequest, Stage3BcellResponse,
    Stage4Request, Stage4Response,
    ReportRequest, ReportResponse,
    AgentError,
)
from fetch.multi.session import PipelineSession
from src.models.pipeline import ReactivityResult, RiskVector

_SESSION_TIMEOUT_S = 120


def create_orchestrator(
    stage1_addr: Optional[str] = None,
    stage2_addr: Optional[str] = None,
    stage3_tcr_addr: Optional[str] = None,
    stage3_bcell_addr: Optional[str] = None,
    stage4_addr: Optional[str] = None,
    report_addr: Optional[str] = None,
) -> Agent:
    """
    Factory that captures specialist agent addresses in a closure.

    Addresses may be passed directly (bureau mode) or resolved from env vars
    (standalone / Agentverse mode):
        STAGE1_AGENT_ADDRESS, STAGE2_AGENT_ADDRESS, STAGE3_TCR_AGENT_ADDRESS,
        STAGE3_BCELL_AGENT_ADDRESS, STAGE4_AGENT_ADDRESS, REPORT_AGENT_ADDRESS
    """
    stage1_addr = stage1_addr or os.getenv("STAGE1_AGENT_ADDRESS")
    stage2_addr = stage2_addr or os.getenv("STAGE2_AGENT_ADDRESS")
    stage3_tcr_addr = stage3_tcr_addr or os.getenv("STAGE3_TCR_AGENT_ADDRESS")
    stage3_bcell_addr = stage3_bcell_addr or os.getenv("STAGE3_BCELL_AGENT_ADDRESS")
    stage4_addr = stage4_addr or os.getenv("STAGE4_AGENT_ADDRESS")
    report_addr = report_addr or os.getenv("REPORT_AGENT_ADDRESS")

    missing = [
        name for name, val in [
            ("stage1_addr / STAGE1_AGENT_ADDRESS", stage1_addr),
            ("stage2_addr / STAGE2_AGENT_ADDRESS", stage2_addr),
            ("stage3_tcr_addr / STAGE3_TCR_AGENT_ADDRESS", stage3_tcr_addr),
            ("stage3_bcell_addr / STAGE3_BCELL_AGENT_ADDRESS", stage3_bcell_addr),
            ("stage4_addr / STAGE4_AGENT_ADDRESS", stage4_addr),
            ("report_addr / REPORT_AGENT_ADDRESS", report_addr),
        ]
        if not val
    ]
    if missing:
        raise ValueError(
            f"Orchestrator missing specialist addresses: {', '.join(missing)}"
        )

    SEED = os.getenv("ORCHESTRATOR_AGENT_SEED", "imm_orchestrator_agent_seed_2026")
    PORT = int(os.getenv("ORCHESTRATOR_AGENT_PORT", "8016"))
    # ORCHESTRATOR_MAILBOX exposes only the orchestrator to Agentverse's relay,
    # keeping all intra-pipeline hops local within the bureau.
    # AGENTVERSE_MAILBOX also works (used when running the orchestrator standalone).
    USE_MAILBOX = bool(os.getenv("ORCHESTRATOR_MAILBOX") or os.getenv("AGENTVERSE_MAILBOX"))

    agent = Agent(
        name="immunogenicity-orchestrator",
        seed=SEED,
        port=PORT,
        endpoint=[f"http://127.0.0.1:{PORT}/submit"],
        mailbox=USE_MAILBOX,
    )

    # Per-run session store: session_id → PipelineSession
    _sessions: dict[str, PipelineSession] = {}

    # ---------------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------------

    def _make_state_dict(session: PipelineSession) -> dict:
        """Serialise all stage results into a plain dict for the ReportAgent."""
        def _dump(obj):
            return obj.model_dump() if obj is not None else None

        return {
            "input":          session.pipeline_input.model_dump(),
            "structural":     _dump(session.structural),
            "hla_binding":    _dump(session.hla_binding),
            "tcr_result":     _dump(session.tcr_result),
            "bcell_result":   _dump(session.bcell_result),
            "reactivity":     _dump(session.reactivity),
            "systems":        _dump(session.systems),
            "risk_vector":    None,
            "clinical_report": None,
            "retry_count":    session.retry_count,
        }

    async def _send_to_report(ctx: Context, session: PipelineSession) -> None:
        """Build reactivity (if needed), then dispatch to the ReportAgent."""
        # Construct ReactivityResult from parallel Stage3 results if present
        if session.tcr_result and session.bcell_result and session.reactivity is None:
            session.reactivity = ReactivityResult(
                tcr=session.tcr_result,
                bcell=session.bcell_result,
                max_tcr_probability=session.tcr_result.binding_probability,
                high_risk_flag=(
                    session.tcr_result.above_threshold
                    or session.bcell_result.epitope_detected
                ),
            )

        state_dict = _make_state_dict(session)
        await ctx.send(
            report_addr,
            ReportRequest(
                session_id=session.session_id,
                pipeline_state_json=json.dumps(state_dict),
            ),
        )

    async def _send_error(ctx: Context, session: PipelineSession, error: str) -> None:
        """Send an error PipelineResponse to the client and clean up."""
        _sessions.pop(session.session_id, None)
        await ctx.send(
            session.client_address,
            PipelineResponse(
                patient_id=session.patient_id,
                recommendation="error",
                overall_risk=0.0,
                structural_risk=0.0,
                immunogenic_risk=0.0,
                reactivity_risk=0.0,
                systems_risk=0.0,
                summary="",
                error=error,
            ),
        )

    # ---------------------------------------------------------------------------
    # Startup
    # ---------------------------------------------------------------------------

    @agent.on_event("startup")
    async def on_startup(ctx: Context) -> None:
        ctx.logger.info(f"Orchestrator started | address={agent.address}")
        ctx.logger.info(f"Agentverse mailbox: {'enabled' if USE_MAILBOX else 'disabled (set ORCHESTRATOR_MAILBOX=1 to enable)'}")
        ctx.logger.info(f"  Stage1   : {stage1_addr[:24]}...")
        ctx.logger.info(f"  Stage2   : {stage2_addr[:24]}...")
        ctx.logger.info(f"  Stage3TCR: {stage3_tcr_addr[:24]}...")
        ctx.logger.info(f"  Stage3BCL: {stage3_bcell_addr[:24]}...")
        ctx.logger.info(f"  Stage4   : {stage4_addr[:24]}...")
        ctx.logger.info(f"  Report   : {report_addr[:24]}...")

    # ---------------------------------------------------------------------------
    # Timeout cleanup
    # ---------------------------------------------------------------------------

    @agent.on_interval(period=30.0)
    async def _cleanup_timed_out_sessions(ctx: Context) -> None:
        now = time.monotonic()
        stale = [
            sid for sid, s in _sessions.items()
            if now - s.created_at > _SESSION_TIMEOUT_S
        ]
        for sid in stale:
            session = _sessions.pop(sid)
            ctx.logger.warning(
                f"[{sid[:8]}] Session timed out for patient={session.patient_id}"
            )
            await ctx.send(
                session.client_address,
                PipelineResponse(
                    patient_id=session.patient_id,
                    recommendation="error",
                    overall_risk=0.0,
                    structural_risk=0.0,
                    immunogenic_risk=0.0,
                    reactivity_risk=0.0,
                    systems_risk=0.0,
                    summary="",
                    error="Pipeline timed out",
                ),
            )

    # ---------------------------------------------------------------------------
    # Entry: client → orchestrator
    # ---------------------------------------------------------------------------

    @agent.on_message(model=PipelineRequest)
    async def handle_pipeline_request(ctx: Context, sender: str, msg: PipelineRequest) -> None:
        from src.models.pipeline import PipelineInput
        session_id = str(uuid.uuid4())
        inp = PipelineInput(
            patient_id=msg.patient_id,
            sequence=msg.sequence,
            edit_positions=msg.edit_positions,
            hla_profile=msg.hla_profile,
        )
        session = PipelineSession(
            session_id=session_id,
            client_address=sender,
            pipeline_input=inp,
        )
        _sessions[session_id] = session
        ctx.logger.info(f"[{session_id[:8]}] Pipeline started | patient_id={msg.patient_id}")

        await ctx.send(
            stage1_addr,
            Stage1Request(
                session_id=session_id,
                patient_id=msg.patient_id,
                sequence=msg.sequence,
                edit_positions=msg.edit_positions,
                hla_profile=msg.hla_profile,
                fallback_mode=False,
            ),
        )

    # ---------------------------------------------------------------------------
    # Stage 1 response — route or retry
    # ---------------------------------------------------------------------------

    @agent.on_message(model=Stage1Response)
    async def handle_stage1_response(ctx: Context, sender: str, msg: Stage1Response) -> None:
        session = _sessions.get(msg.session_id)
        if session is None:
            return

        from src.models.pipeline import StructuralResult
        structural = StructuralResult.model_validate_json(msg.structural_json)
        ctx.logger.info(
            f"[{msg.session_id[:8]}] Stage1 done | "
            f"pLDDT={structural.plddt_score:.1f} confidence={structural.confidence}"
        )

        # Retry once on low structural confidence
        if structural.confidence == "low" and session.retry_count == 0:
            session.retry_count += 1
            ctx.logger.info(f"[{msg.session_id[:8]}] Low pLDDT — retrying in fallback mode")
            await ctx.send(
                stage1_addr,
                Stage1Request(
                    session_id=msg.session_id,
                    patient_id=session.patient_id,
                    sequence=session.pipeline_input.sequence,
                    edit_positions=session.pipeline_input.edit_positions,
                    hla_profile=session.pipeline_input.hla_profile,
                    fallback_mode=True,
                ),
            )
            return

        session.structural = structural
        await ctx.send(
            stage2_addr,
            Stage2Request(
                session_id=msg.session_id,
                input_json=session.pipeline_input.model_dump_json(),
                structural_json=msg.structural_json,
            ),
        )

    # ---------------------------------------------------------------------------
    # Stage 2 response — always fan out to parallel Stage 3
    # ---------------------------------------------------------------------------

    @agent.on_message(model=Stage2Response)
    async def handle_stage2_response(ctx: Context, sender: str, msg: Stage2Response) -> None:
        session = _sessions.get(msg.session_id)
        if session is None:
            return

        from src.models.pipeline import HLABindingResult
        hla = HLABindingResult.model_validate_json(msg.hla_binding_json)
        session.hla_binding = hla
        ctx.logger.info(
            f"[{msg.session_id[:8]}] Stage2 done | "
            f"ClassI_rank={hla.top_class_i_rank:.2f} ClassII_rank={hla.top_class_ii_rank:.2f}"
        )

        # Fan out to both Stage 3 branches simultaneously
        input_json = session.pipeline_input.model_dump_json()
        structural_json = session.structural.model_dump_json()

        await ctx.send(
            stage3_tcr_addr,
            Stage3TcrRequest(
                session_id=msg.session_id,
                input_json=input_json,
                hla_binding_json=msg.hla_binding_json,
            ),
        )
        await ctx.send(
            stage3_bcell_addr,
            Stage3BcellRequest(
                session_id=msg.session_id,
                input_json=input_json,
                structural_json=structural_json,
            ),
        )

    # ---------------------------------------------------------------------------
    # Stage 3 responses — join barrier (whichever arrives second proceeds)
    # ---------------------------------------------------------------------------

    async def _proceed_after_stage3(ctx: Context, session: PipelineSession) -> None:
        high_risk = (
            session.tcr_result.above_threshold
            or session.bcell_result.epitope_detected
        )
        ctx.logger.info(
            f"[{session.session_id[:8]}] Stage3 join | "
            f"TCR above_threshold={session.tcr_result.above_threshold} "
            f"BCell epitope={session.bcell_result.epitope_detected} "
            f"high_risk={high_risk}"
        )

        await ctx.send(
            stage4_addr,
            Stage4Request(
                session_id=session.session_id,
                input_json=session.pipeline_input.model_dump_json(),
            ),
        )

    @agent.on_message(model=Stage3TcrResponse)
    async def handle_stage3_tcr(ctx: Context, sender: str, msg: Stage3TcrResponse) -> None:
        session = _sessions.get(msg.session_id)
        if session is None:
            return

        from src.models.pipeline import TCRResult
        session.tcr_result = TCRResult.model_validate_json(msg.tcr_json)
        session.tcr_done = True
        ctx.logger.info(
            f"[{msg.session_id[:8]}] Stage3 TCR done | "
            f"prob={session.tcr_result.binding_probability:.2f} "
            f"above_threshold={session.tcr_result.above_threshold}"
        )

        if session.bcell_done:
            await _proceed_after_stage3(ctx, session)

    @agent.on_message(model=Stage3BcellResponse)
    async def handle_stage3_bcell(ctx: Context, sender: str, msg: Stage3BcellResponse) -> None:
        session = _sessions.get(msg.session_id)
        if session is None:
            return

        from src.models.pipeline import BCellResult
        session.bcell_result = BCellResult.model_validate_json(msg.bcell_json)
        session.bcell_done = True
        ctx.logger.info(
            f"[{msg.session_id[:8]}] Stage3 BCell done | "
            f"bcell={session.bcell_result.bcell_score:.2f} "
            f"epitope={session.bcell_result.epitope_detected}"
        )

        if session.tcr_done:
            await _proceed_after_stage3(ctx, session)

    # ---------------------------------------------------------------------------
    # Stage 4 response
    # ---------------------------------------------------------------------------

    @agent.on_message(model=Stage4Response)
    async def handle_stage4_response(ctx: Context, sender: str, msg: Stage4Response) -> None:
        session = _sessions.get(msg.session_id)
        if session is None:
            return

        from src.models.pipeline import SystemsResult
        session.systems = SystemsResult.model_validate_json(msg.systems_json)
        ctx.logger.info(
            f"[{msg.session_id[:8]}] Stage4 done | "
            f"stability={session.systems.overall_stability_score:.2f}"
        )
        await _send_to_report(ctx, session)

    # ---------------------------------------------------------------------------
    # Report response — final: reply to client and clean up
    # ---------------------------------------------------------------------------

    @agent.on_message(model=ReportResponse)
    async def handle_report_response(ctx: Context, sender: str, msg: ReportResponse) -> None:
        session = _sessions.pop(msg.session_id, None)
        if session is None:
            return

        rv = RiskVector.model_validate_json(msg.risk_vector_json)
        ctx.logger.info(
            f"[{msg.session_id[:8]}] Pipeline complete | "
            f"patient={session.patient_id} recommendation={rv.recommendation} "
            f"overall={rv.overall_risk:.3f}"
        )

        await ctx.send(
            session.client_address,
            PipelineResponse(
                patient_id=session.patient_id,
                recommendation=rv.recommendation,
                overall_risk=rv.overall_risk,
                structural_risk=rv.structural_risk,
                immunogenic_risk=rv.immunogenic_risk,
                reactivity_risk=rv.reactivity_risk,
                systems_risk=rv.systems_risk,

                summary=rv.summary,
                clinical_report_json=msg.clinical_report_json,
            ),
        )

    # ---------------------------------------------------------------------------
    # Error handler — any specialist agent failure
    # ---------------------------------------------------------------------------

    @agent.on_message(model=AgentError)
    async def handle_agent_error(ctx: Context, sender: str, msg: AgentError) -> None:
        ctx.logger.error(
            f"[{msg.session_id[:8]}] Error in {msg.stage}: {msg.error}"
        )
        session = _sessions.get(msg.session_id)
        if session:
            await _send_error(ctx, session, f"{msg.stage}: {msg.error}")

    return agent


if __name__ == "__main__":
    # Standalone mode: all specialist addresses must be set via env vars.
    # Run `uv run python -m fetch.bureau_multi` once locally (without mailbox
    # keys) to print every agent's address, then export them before running
    # each agent standalone.
    create_orchestrator().run()
