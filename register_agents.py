"""
Register all 7 pipeline agents on Agentverse.

Usage:
    export AGENTVERSE_KEY=<your Agentverse API key>
    uv run python register_agents.py

Each agent is registered with its existing seed (so the address is identical
to what your running agents use) and its local port as the endpoint.

Required env vars:
    AGENTVERSE_KEY   — Agentverse API key (from agentverse.ai account settings)

Optional env vars (override default seeds if you customised them):
    ORCHESTRATOR_AGENT_SEED, STAGE1_AGENT_SEED, STAGE2_AGENT_SEED,
    STAGE3_TCR_AGENT_SEED, STAGE3_BCELL_AGENT_SEED,
    STAGE4_AGENT_SEED, REPORT_AGENT_SEED
"""

import os
import sys

from uagents_core.utils.registration import (
    register_chat_agent,
    RegistrationRequestCredentials,
)

AGENTVERSE_KEY = os.environ.get("AGENTVERSE_KEY")
if not AGENTVERSE_KEY:
    print("ERROR: AGENTVERSE_KEY env var is not set.")
    print("Get your API key from https://agentverse.ai (account settings).")
    sys.exit(1)

AGENTS = [
    {
        "name": "immunogenicity-orchestrator",
        "seed_env": "ORCHESTRATOR_AGENT_SEED",
        "seed_default": "imm_orchestrator_agent_seed_2026",
        "port": int(os.getenv("ORCHESTRATOR_AGENT_PORT", "8016")),
        "description": (
            "Orchestrates the multi-stage gene therapy safety pipeline. "
            "Accepts PipelineRequest, routes across specialist agents, "
            "and returns a PipelineResponse with a risk vector and clinical summary."
        ),
    },
    {
        "name": "stage1-structural",
        "seed_env": "STAGE1_AGENT_SEED",
        "seed_default": "imm_stage1_agent_seed_2026",
        "port": int(os.getenv("STAGE1_AGENT_PORT", "8010")),
        "description": (
            "Stage 1 — Structural modelling. Predicts 3D protein conformation "
            "and surface exposure (SASA) for an edited sequence using ESMFold."
        ),
    },
    {
        "name": "stage2-hla",
        "seed_env": "STAGE2_AGENT_SEED",
        "seed_default": "imm_stage2_agent_seed_2026",
        "port": int(os.getenv("STAGE2_AGENT_PORT", "8011")),
        "description": (
            "Stage 2 — HLA antigen presentation. Scores peptide binding affinity "
            "against a patient's HLA profile (Class I + II) via NetMHCpan."
        ),
    },
    {
        "name": "stage3-tcr",
        "seed_env": "STAGE3_TCR_AGENT_SEED",
        "seed_default": "imm_stage3_tcr_agent_seed_2026",
        "port": int(os.getenv("STAGE3_TCR_AGENT_PORT", "8012")),
        "description": (
            "Stage 3a — T-cell reactivity. Scores TCR binding probability "
            "for the top HLA-presented peptide using NetTCR-2.0."
        ),
    },
    {
        "name": "stage3-bcell",
        "seed_env": "STAGE3_BCELL_AGENT_SEED",
        "seed_default": "imm_stage3_bcell_agent_seed_2026",
        "port": int(os.getenv("STAGE3_BCELL_AGENT_PORT", "8013")),
        "description": (
            "Stage 3b — B-cell reactivity. Predicts linear B-cell epitopes "
            "in the edit zone via BepiPred (IEDB REST API)."
        ),
    },
    {
        "name": "stage4-systems",
        "seed_env": "STAGE4_AGENT_SEED",
        "seed_default": "imm_stage4_agent_seed_2026",
        "port": int(os.getenv("STAGE4_AGENT_PORT", "8014")),
        "description": (
            "Stage 4 — Systems dynamics. Simulates transcriptome perturbation, "
            "cryptic splice events, and apoptotic signalling after a gene edit."
        ),
    },
    {
        "name": "report-agent",
        "seed_env": "REPORT_AGENT_SEED",
        "seed_default": "imm_report_agent_seed_2026",
        "port": int(os.getenv("REPORT_AGENT_PORT", "8015")),
        "description": (
            "Report — Risk aggregation and LLM clinical summary. Combines stage "
            "outputs into a weighted risk vector and generates a physician-readable "
            "report via Claude or ASI:One."
        ),
    },
]


def main():
    print(f"Registering {len(AGENTS)} agents on Agentverse...\n")
    success = 0
    failed = 0

    for agent in AGENTS:
        seed = os.getenv(agent["seed_env"], agent["seed_default"])
        endpoint = f"http://localhost:{agent['port']}/submit"

        try:
            ok = register_chat_agent(
                name=agent["name"],
                endpoint=endpoint,
                active=True,
                credentials=RegistrationRequestCredentials(
                    agentverse_api_key=AGENTVERSE_KEY,
                    agent_seed_phrase=seed,
                ),
                description=agent["description"],
                metadata={"categories": ["healthcare", "bioinformatics"]},
            )
            if ok:
                print(f"  OK  {agent['name']} (port {agent['port']})")
                success += 1
            else:
                print(f"  FAIL  {agent['name']} — register_chat_agent returned False")
                failed += 1
        except Exception as exc:
            print(f"  FAIL  {agent['name']} — {exc}")
            failed += 1

    print(f"\n{success}/{len(AGENTS)} agents registered.")
    if failed:
        print("Re-run to retry failed registrations.")
        sys.exit(1)


if __name__ == "__main__":
    main()
