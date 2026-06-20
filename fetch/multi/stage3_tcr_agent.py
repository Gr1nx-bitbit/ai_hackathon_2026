"""
Stage 3a — T-Cell Reactivity Agent

Wraps TCRTool.predict() (NetTCR-2.0 in production).
Runs in parallel with Stage3BcellAgent — both receive their requests from
the orchestrator simultaneously and respond independently.
"""

import asyncio
import os

try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from uagents import Agent, Context

from fetch.multi.messages import Stage3TcrRequest, Stage3TcrResponse, AgentError
from src.models.pipeline import PipelineInput, HLABindingResult
from src.tools.registry import get_tcr_tool

SEED = os.getenv("STAGE3_TCR_AGENT_SEED", "imm_stage3_tcr_agent_seed_2026")
PORT = int(os.getenv("STAGE3_TCR_AGENT_PORT", "8012"))

agent = Agent(
    name="stage3-tcr",
    seed=SEED,
    port=PORT,
    endpoint=[f"http://127.0.0.1:{PORT}/submit"],
)


@agent.on_event("startup")
async def on_startup(ctx: Context) -> None:
    ctx.logger.info(f"Stage3TcrAgent started | address={agent.address}")


@agent.on_message(model=Stage3TcrRequest, replies={Stage3TcrResponse, AgentError})
async def handle(ctx: Context, sender: str, msg: Stage3TcrRequest) -> None:
    ctx.logger.info(f"[{msg.session_id[:8]}] Stage3 TCR")
    try:
        inp = PipelineInput.model_validate_json(msg.input_json)
        hla_binding = HLABindingResult.model_validate_json(msg.hla_binding_json)

        result = await asyncio.to_thread(get_tcr_tool().predict, inp, hla_binding)
        await ctx.send(
            sender,
            Stage3TcrResponse(
                session_id=msg.session_id,
                tcr_json=result.model_dump_json(),
            ),
        )
    except Exception as exc:
        ctx.logger.error(f"[{msg.session_id[:8]}] Stage3TCR error: {exc}")
        await ctx.send(sender, AgentError(session_id=msg.session_id, stage="stage3_tcr", error=str(exc)))


if __name__ == "__main__":
    agent.run()
