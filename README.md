# Gene Therapy Safety Screener

Multi-stage, patient-personalised in silico immunogenicity and systems safety screening for gene editing therapies. Detects immune rejection risk and cell-autonomous disruption before a therapy reaches the wet lab.

## Problem

Gene therapy edits can trigger two independent failure modes:

1. **Immunogenic rejection** — the immune system recognises the modified protein as foreign, mounts a T-cell or antibody response, and destroys transduced cells.
2. **Systems disruption** — even if the immune system tolerates the edit, cellular machinery may not: cryptic splice sites, altered transcription factor binding, or apoptotic signalling.

Current in-clinic safety screening is slow, expensive, and happens late in development. This pipeline runs in seconds.

## Pipeline

```
Input: patient sequence + edit positions + HLA profile
  │
  ▼
Stage 1 — Structural Modelling
  ESMFold (ESM Atlas REST API) → pLDDT confidence + SASA surface exposure
  Low confidence → fallback retry
  │
  ▼
Stage 2 — HLA Binding Prediction
  IEDB REST API (NetMHCpan-4.1 Class I + NetMHCIIpan-4.0 Class II)
  Both gates clear → early exit (safe — no peptide can be presented)
  │
  ▼
Stage 3 — Immune Reactivity [parallel branches]
  3a: T-cell — NetTCR-2.0 TCR binding probability
  3b: B-cell — BepiPred via IEDB (linear epitope prediction)
  Either flag → early exit (high risk — adaptive immunity activated)
  │
  ▼
Stage 4 — Systems Dynamics
  Transcriptome perturbation, splice-site disruption, apoptosis signalling
  │
  ▼
Report — ASI:One or Claude (claude-opus-4-6)
  Structured clinical summary: headline, stage findings, risk rationale,
  mitigation suggestions, confidence caveats
  │
  ▼
Output: SAFE / CAUTION / HIGH RISK + risk vector + clinical report
```

## Architecture

The pipeline has two parallel implementations that share the same tool layer:

- **LangGraph graph** (`src/agents/graph.py`) — compiled StateGraph used by the Streamlit web app and the terminal demo
- **Fetch AI multi-agent bureau** (`fetch/bureau_multi.py`) — seven specialist uAgents (one per stage + an orchestrator) that communicate via the Agentverse message protocol

Both use the same `PipelineRequest` / `PipelineResponse` contract and the same underlying tools.

## Real Tools

| Stage | Tool | Status |
|---|---|---|
| Stage 1 | ESMFold via ESM Atlas REST API | `ESMFOLD_ENABLED=1` |
| Stage 2 | IEDB REST API (NetMHCpan / NetMHCIIpan) | `IEDB_ENABLED=1` |
| Stage 3b | BepiPred via IEDB REST API | `BEPIPRED_ENABLED=1` |
| Report | ASI:One | `ASI1_API_KEY=<key>` |
| Report | Claude (claude-opus-4-6) | `ANTHROPIC_API_KEY=<key>` |

Stages 3a (NetTCR-2.0) and 4 (GenBio AIDO) have mock implementations. The abstract base classes in `src/tools/base.py` map 1:1 to real implementations — no graph changes required to wire them.

## Quick Start

See [SETUP.md](SETUP.md) for full installation and configuration instructions.

```bash
# Install
uv sync

# Run the web app (recommended)
uv run streamlit run app.py

# Run the terminal demo (no API keys required)
uv run python demo.py

# Run with all available real tools
export ESMFOLD_ENABLED=1
export IEDB_ENABLED=1
export BEPIPRED_ENABLED=1
export ASI1_API_KEY=<your key>
uv run streamlit run app.py
```

## Project Structure

```
src/
  models/pipeline.py         Pydantic schemas (stage I/O + PipelineState)
  tools/
    base.py                  Abstract base classes for each tool type
    registry.py              Tool factory — controls mock / real selection
    mock/                    Mock implementations (all 4 stages)
    real/
      structural_tool.py     ESMFold via ESM Atlas + HuggingFace
      hla_tool.py            IEDB NetMHCpan Class I + II
      bcell_tool.py          BepiPred via IEDB
    report/
      asi1_tool.py           ASI:One clinical report
      claude_tool.py         Claude (claude-opus-4-6) clinical report
      mock_tool.py           Canned scenario-specific reports
  agents/
    nodes.py                 LangGraph node functions and routing logic
    graph.py                 StateGraph definition and compilation
  scoring.py                 Risk vector aggregation

fetch/
  messages.py                Public message contract
  pipeline_agent.py          Monolithic uAgent
  bureau.py                  Monolithic bureau
  bureau_multi.py            Multi-agent bureau (7 agents + orchestrator)
  multi/                     Specialist agent implementations

app.py                       Streamlit web app
demo.py                      Rich terminal demo — 4 scenarios
```

## Scenarios

| Scenario | Description |
|---|---|
| A — HIGH_RISK | Full pipeline, strong HLA binder, TCR + B-cell reactivity flags, high_risk result |
| B — EARLY_EXIT | Pipeline terminates at Stage 2 (both HLA class thresholds clear) |
| C — SYSTEMS_FAILURE | Immune system tolerates the edit; Stage 4 detects cellular disruption |
| D — ALL_CLEAR | Full pipeline, safe result |
