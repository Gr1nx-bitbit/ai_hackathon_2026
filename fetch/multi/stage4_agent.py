"""
Stage 4 — Systems Dynamics Agent

Wraps SystemsTool.predict() (GenBio AI AIDO in production).
Only reached when Stage 3 reactivity is within tolerance.
"""

import asyncio
import os

try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from uagents import Agent, Context

from fetch.multi.messages import Stage4Request, Stage4Response, AgentError
from src.models.pipeline import PipelineInput
from src.tools.registry import get_systems_tool

SEED = os.getenv("STAGE4_AGENT_SEED", "imm_stage4_agent_seed_2026")
PORT = int(os.getenv("STAGE4_AGENT_PORT", "8014"))
USE_MAILBOX = bool(os.getenv("AGENTVERSE_MAILBOX"))

agent = Agent(
    name="stage4-systems",
    seed=SEED,
    port=PORT,
    endpoint=[f"http://127.0.0.1:{PORT}/submit"],
    mailbox=USE_MAILBOX,
)


@agent.on_event("startup")
async def on_startup(ctx: Context) -> None:
    ctx.logger.info(f"Stage4Agent started | address={agent.address}")
    ctx.logger.info(f"Agentverse mailbox: {'enabled' if USE_MAILBOX else 'disabled (set AGENTVERSE_MAILBOX=1 to enable)'}")


@agent.on_message(model=Stage4Request, replies={Stage4Response, AgentError})
async def handle(ctx: Context, sender: str, msg: Stage4Request) -> None:
    ctx.logger.info(f"[{msg.session_id[:8]}] Stage4 systems dynamics")
    try:
        inp = PipelineInput.model_validate_json(msg.input_json)

        result = await asyncio.to_thread(get_systems_tool().predict, inp)
        await ctx.send(
            sender,
            Stage4Response(
                session_id=msg.session_id,
                systems_json=result.model_dump_json(),
            ),
        )
    except Exception as exc:
        ctx.logger.error(f"[{msg.session_id[:8]}] Stage4 error: {exc}")
        await ctx.send(sender, AgentError(session_id=msg.session_id, stage="stage4", error=str(exc)))


if __name__ == "__main__":
    agent.run()
