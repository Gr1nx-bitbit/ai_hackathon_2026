"""
Report Agent — Risk Aggregation + LLM Clinical Summary

Receives the full serialised pipeline state from the orchestrator, runs
compute_risk_vector() (pure Python, inline), then calls the configured
ReportTool (Claude / ASI:One / mock) in a thread.

Owning scoring here rather than in the orchestrator keeps the orchestrator
as a pure router and gives this agent a clean, self-contained contract:
state in → (risk_vector, clinical_report) out.
"""

import asyncio
import json
import os
from typing import Optional

try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from uagents import Agent, Context

from fetch.multi.messages import ReportRequest, ReportResponse, AgentError
from src.models.pipeline import (
    PipelineInput,
    StructuralResult,
    HLABindingResult,
    TCRResult,
    BCellResult,
    ReactivityResult,
    SystemsResult,
    RiskVector,
    PipelineState,
)
from src.scoring import compute_risk_vector
from src.tools.registry import get_report_tool

SEED = os.getenv("REPORT_AGENT_SEED", "imm_report_agent_seed_2026")
PORT = int(os.getenv("REPORT_AGENT_PORT", "8015"))

agent = Agent(
    name="report-agent",
    seed=SEED,
    port=PORT,
    endpoint=[f"http://127.0.0.1:{PORT}/submit"],
)


def _reconstruct_state(raw: dict) -> PipelineState:
    """Rebuild a typed PipelineState from the JSON-deserialised dict."""
    def maybe(cls, data):
        return cls.model_validate(data) if data is not None else None

    return {
        "input":          PipelineInput.model_validate(raw["input"]),
        "structural":     maybe(StructuralResult, raw.get("structural")),
        "hla_binding":    maybe(HLABindingResult, raw.get("hla_binding")),
        "tcr_result":     maybe(TCRResult, raw.get("tcr_result")),
        "bcell_result":   maybe(BCellResult, raw.get("bcell_result")),
        "reactivity":     maybe(ReactivityResult, raw.get("reactivity")),
        "systems":        maybe(SystemsResult, raw.get("systems")),
        "risk_vector":    None,
        "clinical_report": None,
        "retry_count":    raw.get("retry_count", 0),
    }


@agent.on_event("startup")
async def on_startup(ctx: Context) -> None:
    ctx.logger.info(f"ReportAgent started | address={agent.address}")


@agent.on_message(model=ReportRequest, replies={ReportResponse, AgentError})
async def handle(ctx: Context, sender: str, msg: ReportRequest) -> None:
    ctx.logger.info(f"[{msg.session_id[:8]}] Report | scoring + LLM summary")
    try:
        raw = json.loads(msg.pipeline_state_json)
        state = _reconstruct_state(raw)

        # Risk aggregation is pure Python — no I/O, safe to call inline
        risk_vector = compute_risk_vector(state)
        state["risk_vector"] = risk_vector

        # LLM call may be slow — run in thread
        report = await asyncio.to_thread(get_report_tool().generate, state)

        await ctx.send(
            sender,
            ReportResponse(
                session_id=msg.session_id,
                risk_vector_json=risk_vector.model_dump_json(),
                clinical_report_json=report.model_dump_json(),
            ),
        )
    except Exception as exc:
        ctx.logger.error(f"[{msg.session_id[:8]}] Report error: {exc}")
        await ctx.send(sender, AgentError(session_id=msg.session_id, stage="report", error=str(exc)))


if __name__ == "__main__":
    agent.run()
