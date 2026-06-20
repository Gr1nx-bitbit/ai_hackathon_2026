# Setup & Getting Started

## Requirements

- Python 3.11 or 3.12 (recommended; tested on 3.12)
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

> **Note on Python 3.14:** uagents may not yet support Python 3.14. Stick to 3.11–3.12 to avoid dependency conflicts.

---

## Installation

```bash
# Clone the repo
git clone <repo-url>
cd ai_hackathon_2026

# Install with uv (recommended)
uv sync

# Or with pip
pip install -r requirements.txt
```

---

## Running the Web App

The recommended way to run the pipeline is the Streamlit web app. It is interactive, shows live pipeline progress, and includes a binding affinity chart and annotated sequence view.

```bash
uv run streamlit run app.py
```

Open `http://localhost:8501` in your browser. Select a scenario from the sidebar and click **Run Pipeline**.

---

## Running the Terminal Demo

A Rich-formatted terminal walkthrough of all four scenarios is also available. No API keys required.

```bash
uv run python demo.py
```

| Scenario | Description |
|---|---|
| A — HIGH_RISK | Full pipeline, strong HLA binder, TCR + B-cell reactivity flags set, high_risk result |
| B — EARLY_EXIT | Pipeline terminates at Stage 2 (both HLA class thresholds clear) |
| C — SYSTEMS_FAILURE | Immune system tolerates the edit; Stage 4 detects cellular disruption |
| D — ALL_CLEAR | Full pipeline runs to completion with a safe result |

---

## Environment Variables

### Report Node (LLM Clinical Summary)

| Variable | Default | Description |
|---|---|---|
| `ASI1_API_KEY` | — | Enables ASI:One report generation. Auto-selected over Claude when set. |
| `ASI1_MODEL` | `asi1-mini` | ASI:One model to use. Check `https://api.asi1.ai/v1/models` for available models. |
| `ASI1_API_BASE_URL` | `https://api.asi1.ai/v1` | Override if the ASI:One endpoint changes. |
| `ANTHROPIC_API_KEY` | — | Enables Claude report generation (`claude-opus-4-6`). Used when `ASI1_API_KEY` is not set. |
| `REPORT_LLM` | `auto` | `auto` — prefers ASI:One → Claude → mock based on which keys are set. `asi1` — force ASI:One. `claude` — force Claude. `mock` — force mock reports. |

### Fetch AI — Monolithic Agent

| Variable | Default | Description |
|---|---|---|
| `PIPELINE_AGENT_SEED` | `immunogenicity_pipeline_agent_seed_2026` | Deterministic seed for the monolithic agent's address. |
| `PIPELINE_AGENT_PORT` | `8000` | Local port. |
| `AGENT_MAILBOX_KEY` | — | Agentverse mailbox key. Required for Agentverse registration. |

### Fetch AI — Multi-Agent Decomposition

Each specialist agent has its own seed and port env var. All default to fixed values so the bureau works out of the box.

| Variable | Default port | Agent |
|---|---|---|
| `ORCHESTRATOR_AGENT_SEED` / `ORCHESTRATOR_AGENT_PORT` | `8016` | Orchestrator |
| `STAGE1_AGENT_SEED` / `STAGE1_AGENT_PORT` | `8010` | Stage 1 — Structural |
| `STAGE2_AGENT_SEED` / `STAGE2_AGENT_PORT` | `8011` | Stage 2 — HLA |
| `STAGE3_TCR_AGENT_SEED` / `STAGE3_TCR_AGENT_PORT` | `8012` | Stage 3 — T-cell |
| `STAGE3_BCELL_AGENT_SEED` / `STAGE3_BCELL_AGENT_PORT` | `8013` | Stage 3 — B-cell |
| `STAGE4_AGENT_SEED` / `STAGE4_AGENT_PORT` | `8014` | Stage 4 — Systems |
| `REPORT_AGENT_SEED` / `REPORT_AGENT_PORT` | `8015` | Report |

### Real Tools

| Variable | Default | Description |
|---|---|---|
| `ESMFOLD_ENABLED` | `0` | Set to `1` to use ESMFold for Stage 1 structure prediction. No download needed. Requires network access. |
| `HUGGINGFACE_API_KEY` | — | HuggingFace token (free at huggingface.co/settings/tokens). When set, uses the HF Inference API (more reliable). Without it, falls back to ESM Atlas (no auth, may be overloaded). |
| `ESMFOLD_API_URL` | auto | Override the ESMFold endpoint. Defaults to HuggingFace if `HUGGINGFACE_API_KEY` is set, ESM Atlas otherwise. |
| `ESMFOLD_TIMEOUT` | `120` | Per-request timeout in seconds (folding takes 10–60 s). |
| `ESMFOLD_MAX_LENGTH` | `400` | Soft sequence-length limit for the free API. Longer sequences are truncated to the edit zone ± context. |
| `ESMFOLD_CONTEXT` | `50` | Flanking residues to include around the edit zone when truncating. |
| `ESMFOLD_VERIFY_SSL` | `1` | Set to `0` to disable SSL certificate verification. |
| `ESMFOLD_REQUEST_DELAY` | `1.0` | Seconds to sleep before each API call. |
| `ESMFOLD_MAX_RETRIES` | `3` | Retries on 429/503 before giving up. |
| `ESMFOLD_RETRY_BACKOFF` | `5.0` | Seconds for the first retry delay (doubles on each subsequent retry). |
| `IEDB_ENABLED` | `0` | Set to `1` to use the IEDB REST API for Stage 2 HLA binding prediction (Class I + Class II). No download needed. Requires network access. |
| `IEDB_API_BASE_URL` | `https://tools-cluster-interface.iedb.org/tools_api` | Override if the IEDB API URL changes. |
| `IEDB_TIMEOUT` | `60` | Per-request timeout in seconds. |
| `IEDB_FULL_SEQUENCE` | `0` | Set to `1` to submit the full protein sequence instead of just the edit zone window. |
| `IEDB_VERIFY_SSL` | `1` | Set to `0` to disable SSL certificate verification. Use if you get SSL errors on a corporate network or with an outdated certificate store. |
| `IEDB_REQUEST_DELAY` | `1.5` | Seconds to sleep between IEDB API calls. The free API throttles bursts from a single IP; increase if you still see 403 errors. |
| `IEDB_MAX_RETRIES` | `3` | Retries on 403/429 before giving up on an allele call. |
| `IEDB_RETRY_BACKOFF` | `4.0` | Seconds for the first retry delay (doubles on each subsequent retry). |
| `BEPIPRED_ENABLED` | `0` | Set to `1` to use BepiPred via IEDB for Stage 3 B-cell linear epitope prediction. No download needed. Requires network access. |
| `BEPIPRED_THRESHOLD` | `0.35` | Per-residue score threshold for epitope annotation (BepiPred published threshold; score range ≈ −1 to +1). |
| `BEPIPRED_MIN_LENGTH` | `4` | Minimum contiguous above-threshold residues to call an epitope segment. |
| `BEPIPRED_CONTEXT` | `15` | Flanking residues to include around the edit zone when submitting to IEDB. |
| `BEPIPRED_FULL_SEQUENCE` | `0` | Set to `1` to submit the full protein sequence instead of just the edit zone window. |
| `PIPELINE_MODE` | `mock` | Set to `real` to switch all tools at once (for future use when all real tools are wired). |

---

## Running with Real Structure Predictions (ESMFold / ESM Atlas)

ESMFold (Meta AI) predicts 3D protein structure in a single neural network forward pass — no multiple sequence alignment, no GPU required. The ESM Atlas public API provides free access. BioPython is used to extract per-residue pLDDT confidence scores and SASA from the returned PDB file.

### Install

```bash
uv sync   # biopython is already in requirements.txt
```

### Run (recommended — HuggingFace, free token required)

Get a free token at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) (read access is enough):

```bash
export ESMFOLD_ENABLED=1
export HUGGINGFACE_API_KEY=hf_...
uv run python demo.py
```

### Run (no token — ESM Atlas, may be overloaded)

```bash
export ESMFOLD_ENABLED=1
uv run python demo.py
```

ESMFold submits the protein sequence (truncated to the edit zone ± 50 residues if the sequence exceeds 400 aa) and returns a PDB structure in ~10–60 seconds. pLDDT and SASA are computed directly from the structure file — no local model weights needed.

> **Note:** The ESM Atlas free endpoint can return 503/504 under load. Set `HUGGINGFACE_API_KEY` for a more reliable experience. On failure the tool returns a conservative fallback result (full exposure assumed) and the pipeline continues normally.

Both stages can be run simultaneously:

```bash
export ESMFOLD_ENABLED=1
export IEDB_ENABLED=1
uv run python demo.py
```

---

## Running with Real HLA Binding Predictions (IEDB REST API)

The IEDB Analysis Resource provides a free public REST API wrapping NetMHCpan (Class I) and NetMHCIIpan (Class II) — the same tools the pipeline would use in full production. No installation beyond `requests` is required and no model weights need to be downloaded.

### Install

```bash
uv sync   # requests is already in requirements.txt
```

### Run

```bash
export IEDB_ENABLED=1
uv run python demo.py
```

The tool submits the sequence window around the edit positions (±15 residues) to the IEDB API for each allele in the patient's HLA profile, returning real %Rank and IC50 values for both Class I and Class II. Because both classes are predicted, the dual-gate early-exit functions correctly — scenarios that would early-exit in mock mode may now proceed to Stage 3 depending on real binding predictions for the given sequences.

> **Note:** Each allele requires a separate HTTP request (~1–3 seconds each). For a patient with 5 alleles, Stage 2 takes ~10–20 seconds. Set `IEDB_FULL_SEQUENCE=1` to screen the entire protein rather than just the edit zone window.

---

## Running with Real B-Cell Epitope Predictions (BepiPred / IEDB REST API)

BepiPred is a random-forest model that predicts linear B-cell epitopes from sequence alone. It is available via the same IEDB Analysis Resource REST API used in Stage 2.

> **Linear vs conformational epitopes:** BepiPred identifies sequential (linear) epitope segments. The majority of real antibody epitopes are conformational (discontinuous in 3D space) — detected by tools such as DiscoTope-3.0, which require a PDB structure as input. For this POC, linear screening is a practical surrogate. See `PROBLEM.md` for a discussion of this trade-off.

### Install

```bash
uv sync   # requests is already in requirements.txt
```

### Run

```bash
export BEPIPRED_ENABLED=1
uv run python demo.py
```

You can combine all three real tools simultaneously:

```bash
export ESMFOLD_ENABLED=1
export IEDB_ENABLED=1
export BEPIPRED_ENABLED=1
uv run python demo.py
```

---

## Running with ASI:One Reports

Set your ASI:One API key to use ASI:One for clinical report generation. ASI:One is auto-selected over Claude when its key is present.

```bash
export ASI1_API_KEY=<your key>
uv run streamlit run app.py
```

To override the model (default: `asi1-mini`):

```bash
export ASI1_MODEL=<model-id>
```

---

## Running with Claude Reports

Set your Anthropic API key and run the demo:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
uv run python demo.py
```

The report node will use `claude-opus-4-6` with adaptive thinking to generate a plain-language clinical summary for each scenario. This adds a few seconds per scenario.

To force mock reports even with the API key set:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export REPORT_LLM=mock
uv run python demo.py
```

---

## Running the Fetch AI Bureau (Local Agent-to-Agent Test)

There are two bureau modes. Both use the same `PipelineRequest` / `PipelineResponse` message contract and the same test client.

### Monolithic bureau

One pipeline agent wraps the full LangGraph graph internally.

```bash
uv run python -m fetch.bureau
```

### Multi-agent bureau

Seven specialist agents connected via an orchestrator. Each stage is an independent agent.

```bash
uv run python -m fetch.bureau_multi
```

Expected output for both: all agents start, the client sends four requests on startup, and the orchestrator (or pipeline agent) logs a recommendation and risk score for each.

> **Note:** Without `AGENT_MAILBOX_KEY` set, uagents will print SSL/gRPC warnings when attempting Almanac registration. This is expected — agents still communicate locally via Bureau. You can safely ignore these.

---

## Registering Agents on Agentverse

### Monolithic agent (single registration)

Register one agent that handles the full pipeline.

1. Create an account at [agentverse.ai](https://agentverse.ai) and create a new agent. Copy the **Mailbox Key**.
2. Set the env var and run:

```bash
export AGENT_MAILBOX_KEY=<your-mailbox-key>
uv run python -m fetch.pipeline_agent
```

The agent prints its deterministic address on startup, registers with the Almanac, and begins listening for `PipelineRequest` messages.

### Multi-agent decomposition (per-stage registration)

Each specialist agent can be registered independently on Agentverse. This lets other agents call individual stages — e.g. a research team could call `Stage2Agent` directly for HLA binding screening without running the full pipeline.

For each agent you want to register:

1. Create a new agent in the Agentverse dashboard. Copy its **Mailbox Key**.
2. Set the corresponding seed env var (so the address is deterministic) and the mailbox key:

```bash
export STAGE2_AGENT_SEED=my-custom-seed   # optional — set a memorable seed
export AGENT_MAILBOX_KEY=<mailbox-key-for-this-agent>
uv run python -m fetch.multi.stage2_agent
```

Repeat for each agent you want on the network. The orchestrator is the entry point for full-pipeline requests; individual stages can be called directly by any agent that knows their address.

**Tip:** Run the bureau once locally without a mailbox key to print all agent addresses:

```bash
uv run python -m fetch.bureau_multi
```

The orchestrator logs all specialist addresses on startup.

### Message contract

The public API is unchanged regardless of deployment mode:

```python
# Send to the monolithic pipeline_agent OR the orchestrator — same contract
PipelineRequest(
    patient_id="PATIENT_001",
    sequence="MVLSPADKTNVK...",
    edit_positions=[47, 48, 49],
    hla_profile=["HLA-A*02:01", "HLA-B*07:02", "HLA-DRB1*01:01"],
)

# Response
PipelineResponse(
    patient_id="PATIENT_001",
    recommendation="high_risk",   # "safe" | "caution" | "high_risk" | "error"
    overall_risk=0.812,
    structural_risk=0.65,
    immunogenic_risk=0.90,
    reactivity_risk=0.86,
    systems_risk=0.60,
    early_exit_stage=None,
    summary="Strong Class I binder detected. TCR activation predicted...",
)
```

---

## Project Structure

```
src/
  models/pipeline.py         All Pydantic schemas (stage I/O + PipelineState)
  tools/
    base.py                  Abstract base classes for each tool type
    registry.py              Tool factory — controls mock ↔ real selection
    mock/                    Mock implementations for all 4 stages
    report/
      claude_tool.py         Claude (claude-opus-4-6) report implementation
      asi1_tool.py           ASI:One stub (wiring instructions inside)
      mock_tool.py           Canned scenario-specific reports
  agents/
    nodes.py                 LangGraph node functions and routing logic
    graph.py                 StateGraph definition and compilation
  scoring.py                 Risk vector aggregation formula

fetch/
  messages.py                Public message contract (PipelineRequest / PipelineResponse)
  pipeline_agent.py          Monolithic uAgent — wraps the full pipeline
  client_agent.py            Test client (shared by both bureaus)
  bureau.py                  Monolithic bureau
  bureau_multi.py            Multi-agent bureau — all 7 agents + orchestrator + client
  multi/
    messages.py              Internal inter-agent message schemas
    session.py               Per-run session state for the orchestrator
    orchestrator.py          Routing and join logic
    stage1_agent.py          Structural modeling
    stage2_agent.py          HLA binding
    stage3_tcr_agent.py      T-cell reactivity
    stage3_bcell_agent.py    B-cell reactivity
    stage4_agent.py          Systems dynamics
    report_agent.py          Risk scoring + LLM report

demo.py                      Rich terminal demo — 4 scenarios
```

---

## Swapping a Mock for a Real Tool

1. Implement the abstract base class from `src/tools/base.py`  
   (e.g., `class AlphaFoldStructuralTool(StructuralTool)`)

2. Register it in `src/tools/registry.py` under the `PIPELINE_MODE=real` branch

3. Set `PIPELINE_MODE=real` and run

No changes to the graph, nodes, scoring, demo, or Fetch agent are required.
