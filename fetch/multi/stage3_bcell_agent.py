"""
Stage 3b — B-Cell Reactivity Agent

Wraps BCellTool.predict() (BepiPred via IEDB REST API in production).
Runs in parallel with Stage3TcrAgent.
"""

import asyncio
import os

try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from uagents import Agent, Context

from fetch.multi.messages import Stage3BcellRequest, Stage3BcellResponse, AgentError
from src.models.pipeline import PipelineInput, StructuralResult
from src.tools.registry import get_bcell_tool

SEED = os.getenv("STAGE3_BCELL_AGENT_SEED", "imm_stage3_bcell_agent_seed_2026")
PORT = int(os.getenv("STAGE3_BCELL_AGENT_PORT", "8013"))

agent = Agent(
    name="stage3-bcell",
    seed=SEED,
    port=PORT,
    endpoint=[f"http://127.0.0.1:{PORT}/submit"],
)


@agent.on_event("startup")
async def on_startup(ctx: Context) -> None:
    ctx.logger.info(f"Stage3BcellAgent started | address={agent.address}")


@agent.on_message(model=Stage3BcellRequest, replies={Stage3BcellResponse, AgentError})
async def handle(ctx: Context, sender: str, msg: Stage3BcellRequest) -> None:
    ctx.logger.info(f"[{msg.session_id[:8]}] Stage3 BCell")
    try:
        inp = PipelineInput.model_validate_json(msg.input_json)
        structural = StructuralResult.model_validate_json(msg.structural_json)

        result = await asyncio.to_thread(get_bcell_tool().predict, inp, structural)
        await ctx.send(
            sender,
            Stage3BcellResponse(
                session_id=msg.session_id,
                bcell_json=result.model_dump_json(),
            ),
        )
    except Exception as exc:
        ctx.logger.error(f"[{msg.session_id[:8]}] Stage3BCell error: {exc}")
        await ctx.send(sender, AgentError(session_id=msg.session_id, stage="stage3_bcell", error=str(exc)))


if __name__ == "__main__":
    agent.run()
