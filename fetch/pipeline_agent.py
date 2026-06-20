"""
Fetch AI uAgent — Immunogenicity Pipeline

This agent registers on Agentverse and exposes the LangGraph pipeline
as a callable agent that any other agent on the network can invoke.

Architecture:
    [Client Agent] --PipelineRequest--> [This Agent] --PipelineResponse--> [Client Agent]
                                              |
                                       LangGraph pipeline
                                       (stages 1-4, mocks or real)

To run standalone:
    uv run python -m fetch.pipeline_agent

To get this agent's address (needed by clients):
    The address is printed on startup. It is deterministic — derived from
    AGENT_SEED — so it will be the same every time you run it.

To register on Agentverse:
    1. Create an account at https://agentverse.ai
    2. Create a new agent and copy the AGENT_MAILBOX_KEY
    3. Set the AGENT_MAILBOX_KEY environment variable
    4. Run the agent — it will register automatically via the mailbox
"""

import asyncio
import os

# Python 3.12+ no longer auto-creates an event loop in the main thread.
# uagents requires one to exist at Agent construction time.
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from uagents import Agent, Context

from fetch.messages import PipelineRequest, PipelineResponse
from src.agents.graph import build_graph
from src.models.pipeline import PipelineInput, PipelineState

# ---------------------------------------------------------------------------
# Agent configuration
# ---------------------------------------------------------------------------

# Seed is deterministic so the agent address never changes between restarts.
# In production, load this from an environment variable or secrets manager.
AGENT_SEED = os.getenv("PIPELINE_AGENT_SEED", "immunogenicity_pipeline_agent_seed_2026")
AGENT_PORT = int(os.getenv("PIPELINE_AGENT_PORT", "8000"))
AGENT_MAILBOX_KEY = os.getenv("AGENT_MAILBOX_KEY")  # Set to enable Agentverse registration

agent_kwargs: dict = dict(
    name="immunogenicity-pipeline",
    seed=AGENT_SEED,
    port=AGENT_PORT,
    endpoint=[f"http://127.0.0.1:{AGENT_PORT}/submit"],
)
if AGENT_MAILBOX_KEY:
    agent_kwargs["mailbox"] = AGENT_MAILBOX_KEY

agent = Agent(**agent_kwargs)

# ---------------------------------------------------------------------------
# Pipeline — built once at module load, reused across all requests
# ---------------------------------------------------------------------------

_pipeline = build_graph()


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

@agent.on_event("startup")
async def on_startup(ctx: Context) -> None:
    ctx.logger.info("Immunogenicity pipeline agent started.")
    ctx.logger.info(f"Address : {agent.address}")
    ctx.logger.info(f"Port    : {AGENT_PORT}")
    if AGENT_MAILBOX_KEY:
        ctx.logger.info("Agentverse mailbox: enabled")
    else:
        ctx.logger.info("Agentverse mailbox: disabled (set AGENT_MAILBOX_KEY to enable)")


@agent.on_message(model=PipelineRequest, replies=PipelineResponse)
async def handle_pipeline_request(
    ctx: Context, sender: str, msg: PipelineRequest
) -> None:
    ctx.logger.info(f"Pipeline request from {sender[:20]}... | patient_id={msg.patient_id}")

    try:
        inp = PipelineInput(
            patient_id=msg.patient_id,
            sequence=msg.sequence,
            edit_positions=msg.edit_positions,
            hla_profile=msg.hla_profile,
        )

        initial_state: PipelineState = {
            "input": inp,
            "structural": None,
            "hla_binding": None,
            "tcr_result": None,
            "bcell_result": None,
            "reactivity": None,
            "systems": None,
            "risk_vector": None,
            "retry_count": 0,
        }

        # LangGraph invoke is synchronous — run it in a thread to avoid
        # blocking the uagents event loop.
        final_state = await asyncio.to_thread(_pipeline.invoke, initial_state)
        rv = final_state["risk_vector"]

        ctx.logger.info(
            f"Pipeline complete | patient_id={msg.patient_id} "
            f"recommendation={rv.recommendation} overall_risk={rv.overall_risk:.3f}"
        )

        await ctx.send(
            sender,
            PipelineResponse(
                patient_id=rv.early_exit_stage and msg.patient_id or msg.patient_id,
                recommendation=rv.recommendation,
                overall_risk=rv.overall_risk,
                structural_risk=rv.structural_risk,
                immunogenic_risk=rv.immunogenic_risk,
                reactivity_risk=rv.reactivity_risk,
                systems_risk=rv.systems_risk,
                early_exit_stage=rv.early_exit_stage,
                summary=rv.summary,
            ),
        )

    except Exception as exc:
        ctx.logger.error(f"Pipeline error for {msg.patient_id}: {exc}")
        await ctx.send(
            sender,
            PipelineResponse(
                patient_id=msg.patient_id,
                recommendation="error",
                overall_risk=0.0,
                structural_risk=0.0,
                immunogenic_risk=0.0,
                reactivity_risk=0.0,
                systems_risk=0.0,
                summary="",
                error=str(exc),
            ),
        )


if __name__ == "__main__":
    agent.run()
