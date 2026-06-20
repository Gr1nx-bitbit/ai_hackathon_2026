"""
Multi-Agent Bureau — runs all 7 specialist agents + orchestrator + test client
in a single process for local end-to-end testing.

Topology:
    client → orchestrator → stage1 → stage2 → [stage3_tcr, stage3_bcell]
                                             → stage3_join → stage4 → report
                                                                     ↓
                                                              → client

Each specialist agent is an independent uAgent with its own address.
The orchestrator is wired with all addresses at construction time — no
hardcoded strings, no env vars needed for local testing.

Run:
    uv run python -m fetch.bureau_multi

To register on Agentverse, set AGENT_MAILBOX_KEY before running.
Individual agents can also be run standalone for separate Agentverse registration:
    uv run python -m fetch.multi.stage1_agent
    uv run python -m fetch.multi.report_agent
    etc.
"""

from uagents import Bureau

# Import specialist agents (each module instantiates its Agent at import time)
from fetch.multi.stage1_agent import agent as stage1_agent
from fetch.multi.stage2_agent import agent as stage2_agent
from fetch.multi.stage3_tcr_agent import agent as stage3_tcr_agent
from fetch.multi.stage3_bcell_agent import agent as stage3_bcell_agent
from fetch.multi.stage4_agent import agent as stage4_agent
from fetch.multi.report_agent import agent as report_agent

# Wire orchestrator with all specialist addresses
from fetch.multi.orchestrator import create_orchestrator

orchestrator = create_orchestrator(
    stage1_addr=stage1_agent.address,
    stage2_addr=stage2_agent.address,
    stage3_tcr_addr=stage3_tcr_agent.address,
    stage3_bcell_addr=stage3_bcell_agent.address,
    stage4_addr=stage4_agent.address,
    report_addr=report_agent.address,
)

bureau = Bureau(
    agents=[
        stage1_agent,
        stage2_agent,
        stage3_tcr_agent,
        stage3_bcell_agent,
        stage4_agent,
        report_agent,
        orchestrator,
    ]
)

if __name__ == "__main__":
    bureau.run()
