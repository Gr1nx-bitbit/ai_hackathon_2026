"""
Multi-Agent Bureau — runs all 7 specialist agents + orchestrator in a single
process for local testing (no Agentverse relay, direct intra-process routing).

For Agentverse demos where each agent is individually reachable, run them in
separate terminals instead — see SETUP.md > Registering Agents on Agentverse.

Run:
    uv run python -m fetch.bureau_multi
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
