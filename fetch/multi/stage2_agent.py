"""
Stage 2 — HLA Antigen Presentation Agent

Wraps HLABindingTool.predict() (NetChop + NetMHCpan in production).
Accepts Stage2Request, returns Stage2Response with early_exit flag embedded
in the serialised HLABindingResult.
"""

import asyncio
import os

try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from uagents import Agent, Context

from fetch.multi.messages import Stage2Request, Stage2Response, AgentError
from src.models.pipeline import PipelineInput, StructuralResult
from src.tools.registry import get_hla_tool

SEED = os.getenv("STAGE2_AGENT_SEED", "imm_stage2_agent_seed_2026")
PORT = int(os.getenv("STAGE2_AGENT_PORT", "8011"))
USE_MAILBOX = bool(os.getenv("AGENTVERSE_MAILBOX"))

agent = Agent(
    name="stage2-hla",
    seed=SEED,
    port=PORT,
    endpoint=[f"http://127.0.0.1:{PORT}/submit"],
    mailbox=USE_MAILBOX,
)


@agent.on_event("startup")
async def on_startup(ctx: Context) -> None:
    ctx.logger.info(f"Stage2Agent started | address={agent.address}")
    ctx.logger.info(f"Agentverse mailbox: {'enabled' if USE_MAILBOX else 'disabled (set AGENTVERSE_MAILBOX=1 to enable)'}")


@agent.on_message(model=Stage2Request, replies={Stage2Response, AgentError})
async def handle(ctx: Context, sender: str, msg: Stage2Request) -> None:
    ctx.logger.info(f"[{msg.session_id[:8]}] Stage2 | HLA binding")
    try:
        inp = PipelineInput.model_validate_json(msg.input_json)
        structural = StructuralResult.model_validate_json(msg.structural_json)

        result = await asyncio.to_thread(get_hla_tool().predict, inp, structural)
        await ctx.send(
            sender,
            Stage2Response(
                session_id=msg.session_id,
                hla_binding_json=result.model_dump_json(),
            ),
        )
    except Exception as exc:
        ctx.logger.error(f"[{msg.session_id[:8]}] Stage2 error: {exc}")
        await ctx.send(sender, AgentError(session_id=msg.session_id, stage="stage2", error=str(exc)))


if __name__ == "__main__":
    agent.run()
