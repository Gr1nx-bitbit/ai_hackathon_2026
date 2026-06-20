"""
Stage 1 — Structural Modeling Agent

Wraps StructuralTool.predict() (AlphaFold3/ESMFold + SASA in production,
mock in POC mode). Accepts Stage1Request, returns Stage1Response.

Each request is independent — no session state here.
The orchestrator manages retry logic based on pLDDT confidence.
"""

import asyncio
import os

try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from uagents import Agent, Context

from fetch.multi.messages import Stage1Request, Stage1Response, AgentError
from src.models.pipeline import PipelineInput
from src.tools.registry import get_structural_tool

SEED = os.getenv("STAGE1_AGENT_SEED", "imm_stage1_agent_seed_2026")
PORT = int(os.getenv("STAGE1_AGENT_PORT", "8010"))
USE_MAILBOX = bool(os.getenv("AGENTVERSE_MAILBOX"))

agent = Agent(
    name="stage1-structural",
    seed=SEED,
    port=PORT,
    endpoint=[f"http://127.0.0.1:{PORT}/submit"],
    mailbox=USE_MAILBOX,
)


@agent.on_event("startup")
async def on_startup(ctx: Context) -> None:
    ctx.logger.info(f"Stage1Agent started | address={agent.address}")
    ctx.logger.info(f"Agentverse mailbox: {'enabled' if USE_MAILBOX else 'disabled (set AGENTVERSE_MAILBOX=1 to enable)'}")


@agent.on_message(model=Stage1Request, replies={Stage1Response, AgentError})
async def handle(ctx: Context, sender: str, msg: Stage1Request) -> None:
    ctx.logger.info(
        f"[{msg.session_id[:8]}] Stage1 | patient={msg.patient_id} "
        f"fallback={msg.fallback_mode}"
    )
    try:
        inp = PipelineInput(
            patient_id=msg.patient_id,
            sequence=msg.sequence,
            edit_positions=msg.edit_positions,
            hla_profile=msg.hla_profile,
        )
        result = await asyncio.to_thread(
            get_structural_tool().predict, inp, msg.fallback_mode
        )
        await ctx.send(
            sender,
            Stage1Response(
                session_id=msg.session_id,
                structural_json=result.model_dump_json(),
            ),
        )
    except Exception as exc:
        ctx.logger.error(f"[{msg.session_id[:8]}] Stage1 error: {exc}")
        await ctx.send(sender, AgentError(session_id=msg.session_id, stage="stage1", error=str(exc)))


if __name__ == "__main__":
    agent.run()
