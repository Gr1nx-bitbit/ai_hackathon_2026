# Architecture

## Overview

The pipeline is a patient-specific, multi-stage in silico safety screening system for gene editing therapies. It evaluates both immunogenic risk (will the immune system destroy the edited cells?) and systems-level risk (will the edit destabilise cellular function even if the immune system tolerates it?).

The pipeline is built on **LangGraph** (state machine), wrapped as a **Fetch AI uAgent** (network transport), and capped with an **LLM report node** (Claude or ASI:One) that translates raw scores into a plain-language clinical report.

---

## Graph Topology

```
START
  │
  ▼
stage1 ──── low pLDDT ──► increment_retry ──► stage1 (retry once, fallback mode)
  │
  ▼ (high/medium confidence, or after retry)
stage2
  │
  ├── early exit (Class I %Rank >2.0 AND Class II %Rank >10.0) ──► aggregate
  │
  ▼ (binders detected)
  ├──────────────────────────────┐
  ▼  [parallel via Send]         ▼
stage3_tcr                  stage3_bcell
  │                              │
  └──────────┬───────────────────┘
             ▼
        stage3_join
             │
             ├── high_risk_flag ──► aggregate
             │
             ▼ (reactivity within tolerance)
           stage4
             │
             ▼
          aggregate
             │
             ▼
           report   ◄── Claude / ASI:One / mock
             │
            END
```

---

## Stages

### Stage 1 — Structural Modeling
**Real tool:** ESMFold via ESM Atlas REST API + BioPython — `src/tools/real/structural_tool.py` (enabled via `ESMFOLD_ENABLED=1`)  
**Mock:** `src/tools/mock/stage1.py`

Predicts 3D protein conformation and calculates per-residue Solvent Accessible Surface Area (SASA). The key output is whether the edited residues are surface-exposed (SASA > 30 Å²) — exposed edits are directly accessible to proteasomal machinery, B-cell receptors, and processing enzymes.

**ESMFold mode (`ESMFOLD_ENABLED=1`):** Submits the protein sequence to the ESM Atlas public REST API. The returned PDB file is parsed with BioPython's ShrakeRupley algorithm to compute per-residue SASA; per-residue pLDDT is read from the B-factor column. Sequences longer than 400 aa are automatically truncated to the edit zone ± 50 flanking residues before submission. Any API or parse failure returns a conservative fallback result (full exposure assumed) rather than raising — this naturally triggers the retry loop below.

**Retry loop:** If pLDDT < 50 (low structural confidence — typically disordered regions), the graph cycles once through `increment_retry → stage1` in fallback mode. Fallback mode skips structure prediction and conservatively assumes full surface exposure.

**Output:** `StructuralResult` — pLDDT score, SASA, exposure flag, confidence tier, fallback flag.

---

### Stage 2 — HLA Antigen Presentation
**Real tools:** NetChop-3.1 (proteasomal cleavage) + NetMHCpan-4.1 / NetMHCIIpan-4.0  
**Real tool:** IEDB REST API (HTTPS) — `src/tools/real/hla_tool.py` (Class I + Class II, enabled via `IEDB_ENABLED=1`)  
**Mock:** `src/tools/mock/stage2.py`

Simulates proteasomal cleavage of the edited sequence into candidate peptides (9-mers for Class I, 15-mers for Class II) and scores their binding affinity against every allele in the patient's HLA profile.

**Early exit gate (both conditions must hold):**
- Class I top `%Rank > 2.0` → no strong or weak binders
- Class II top `%Rank > 10.0` → no binders

If both pass, antigen presentation risk is negligible and the pipeline exits early. The gate is intentionally conservative: MHC Class II has an open groove that accepts a wider peptide range, so requiring both classes to clear their threshold prevents false negatives.

**IEDB mode (`IEDB_ENABLED=1`):** Calls the IEDB Analysis Resource REST API (free, no API key) with NetMHCpan-4.1 for Class I and NetMHCIIpan-4.0 for Class II. Only the sequence window around the edit positions (±15 residues) is submitted by default, keeping requests fast. Because both classes are predicted, the dual-gate early-exit functions correctly. If no Class II alleles are present in the patient's HLA profile, `top_class_ii_rank` is set to `0.0` (conservative). No local model weights required — works on any Python version.

**Output:** `HLABindingResult` — ranked binder list per class, top `%Rank`, IC50, `early_exit` flag.

---

### Stage 3 — Immune Reactivity (parallel branches)
**Real tools:** NetTCR-2.0 (T-cell), DiscoTope-3.0 (B-cell)  
**Mock:** `src/tools/mock/stage3.py`

The two branches run in parallel via LangGraph's `Send` API — each receives the full pipeline state independently and writes back to its own state field (`tcr_result`, `bcell_result`). LangGraph waits for both before running `stage3_join`.

**T-cell branch:** NetTCR-2.0 scores the top Class I binder from Stage 2 for TCR recognition probability. Threshold: 0.5. Above → T-cell activation is predicted.

**B-cell branch:** BepiPred scores the edit zone sequence window for linear B-cell epitope likelihood via the IEDB REST API. Threshold: 0.5. Above → neutralising antibody response is predicted. (Conformational epitope detection — e.g., DiscoTope-3.0 — would be applied to the Stage 1 PDB in a full production system; see PROBLEM.md.)

**High-risk early exit:** If either branch flags (`above_threshold=True` or `epitope_detected=True`), `stage3_join` sets `high_risk_flag=True` and the graph exits to `aggregate`, skipping Stage 4 (immune rejection would precede systems-level dysfunction).

**Output:** `TCRResult`, `BCellResult` (parallel) → `ReactivityResult` (joined).

---

### Stage 4 — Systems Dynamics
**Real tool:** GenBio AI AIDO (`ModelGenerator`) — AIDO.RNA, AIDO.DNA, AIDO.Cell  
**Mock:** `src/tools/mock/stage4.py`

Simulates the functional aftermath of the edit inside the living cell ecosystem:

- **AIDO.RNA / AIDO.DNA:** Checks whether the edit introduces cryptic splice donor/acceptor sites (delta PSI > 0.1 = significant isoform shift).
- **AIDO.Cell:** Runs a whole-transcriptome single-cell perturbation simulation across target tissues (liver, HEK293). Outputs per-gene log₂ fold-change vectors and a housekeeping network stability score (0–1).

Toxicity is flagged when apoptotic (CASP3, BAX) or integrated stress response (ATF4, DDIT3) genes are significantly upregulated, or when anti-apoptotic genes (BCL2) and mitochondrial components (TFAM, NDUFB8) are suppressed.

**Output:** `SystemsResult` — `SpliceResult` + `PerturbationResult` per tissue + stability score.

---

### Aggregate — Risk Scoring
**Code:** `src/scoring.py`

Combines all stage outputs into a `RiskVector` using a weighted sum:

```
overall_risk = 0.10 × structural_risk
             + 0.35 × immunogenic_risk
             + 0.35 × reactivity_risk
             + 0.20 × systems_risk
```

Weights reflect clinical priority: immunogenic and reactivity risk are the primary failure mode for gene therapies (T-cell rejection eliminates therapeutic cells). Systems risk is serious but secondary — cellular disruption without immune activation is slower-acting and more recoverable.

| Overall score | Recommendation |
|---|---|
| < 0.25 | `safe` |
| 0.25 – 0.55 | `caution` |
| ≥ 0.55 | `high_risk` |

Individual dimension scores use tiered formulas:
- **Structural risk:** surface exposure + pLDDT confidence weighting
- **Immunogenic risk:** tiered `%Rank` → risk mapping (strong binder < 0.5% → 0.90; weak binder < 2.0% → 0.40; no binder → decays to 0.05)
- **Reactivity risk:** weighted average of TCR binding probability and B-cell epitope flag
- **Systems risk:** transcriptome instability + toxicity penalty for apoptotic signatures

---

### Report Node — LLM Clinical Summary
**Code:** `src/tools/report/`

The final stage calls an LLM to translate the `RiskVector` and all stage outputs into a structured `ClinicalReport` — a plain-language document for physician review with stage-by-stage findings, risk rationale, and mitigation suggestions.

**LLM selection** (via `REPORT_LLM` env var + API key detection):

| `REPORT_LLM` | API key required | Model |
|---|---|---|
| `auto` (default) | `ANTHROPIC_API_KEY` | `claude-opus-4-6` with adaptive thinking |
| `claude` | `ANTHROPIC_API_KEY` | `claude-opus-4-6` with adaptive thinking |
| `asi1` | `ASI1_API_KEY` | ASI:One (stub — see `asi1_tool.py`) |
| `mock` | none | Scenario-specific canned reports |

Claude uses `client.messages.parse()` with `output_format=ClinicalReport` for validated structured output. The `ClinicalReport` Pydantic schema enforces: `headline`, `stage_findings`, `risk_rationale`, `mitigation_suggestions`, `confidence_note`.

---

## Fetch AI Integration
**Code:** `fetch/`

The pipeline is exposed on the Agentverse network in two configurations that share the same public message contract.

### Monolithic Agent (`fetch/pipeline_agent.py`)

A single uAgent that wraps the full LangGraph pipeline internally. Simple to deploy — one process, one address.

```
[Client Agent] ──PipelineRequest──► [Pipeline Agent] ──PipelineResponse──► [Client Agent]
                                           │
                                    LangGraph pipeline (stages 1–4)
```

### Multi-Agent Decomposition (`fetch/multi/`)

Each pipeline stage is an independent specialist agent. An orchestrator agent handles routing, session state, and the parallel Stage 3 join — replicating the LangGraph graph topology in the Agentverse message-passing model.

```
[Client] ──PipelineRequest──► [Orchestrator]
                                    │
                              ┌─────▼──────┐
                              │ Stage1Agent │  (structural)
                              └─────┬──────┘
                                    │  retry loop if pLDDT low
                              ┌─────▼──────┐
                              │ Stage2Agent │  (HLA binding)
                              └──┬──────┬──┘
                    early exit   │      │  binders detected
                                 │   ┌──▼──────────────────┐
                                 │   │ Stage3TcrAgent       │  (parallel)
                                 │   │ Stage3BcellAgent     │  (parallel)
                                 │   └──────────┬──────────┘
                                 │              │  join (both done)
                                 │   ┌──────────▼──────────┐
                                 │   │ Stage4Agent          │  (systems)
                                 │   └──────────┬──────────┘
                                 │              │
                              ┌──▼──────────────▼──┐
                              │    ReportAgent      │  (scoring + LLM)
                              └────────┬────────────┘
                                       │
                        ◄──PipelineResponse──┘
```

Each specialist agent can be registered on Agentverse independently, making any stage callable by any other agent on the network — a research team could call `Stage2Agent` directly without running the full pipeline.

**Session state:** The orchestrator maintains a per-run `PipelineSession` (keyed by UUID) across async message hops. Stage 3 parallel branches synchronise via `tcr_done` / `bcell_done` flags — whichever response arrives second triggers the join. Sessions time out after 120 seconds if a specialist agent fails to respond.

**Serialisation:** Complex Pydantic models travel as JSON strings between agents (`model_dump_json()` / `model_validate_json()`). The public `PipelineRequest` / `PipelineResponse` contract is unchanged — clients don't need to know which deployment mode is running.

**Message contract** (`fetch/messages.py`):
- `PipelineRequest` — patient_id, sequence, edit_positions, hla_profile
- `PipelineResponse` — full risk vector fields + summary + optional error

Internal inter-agent messages are defined in `fetch/multi/messages.py`.

For local testing, `fetch/bureau.py` (monolithic) or `fetch/bureau_multi.py` (decomposed) runs all agents in a single process. For Agentverse registration, set `AGENT_MAILBOX_KEY` — agents register automatically on startup.

---

## Mock / Real Swap Pattern

Every tool in the pipeline implements an abstract base class from `src/tools/base.py`. Graph nodes call only the interface — never the concrete implementation. Swapping a mock for a real binary is a two-step operation:

1. Implement the ABC (e.g., `class AlphaFoldStructuralTool(StructuralTool)`)
2. Register it in `src/tools/registry.py` and set `PIPELINE_MODE=real`

No changes to the graph, nodes, scoring, or demo are required.

---

## File Structure

```
src/
  models/pipeline.py         Pydantic schemas for all stage I/O + PipelineState
  tools/
    base.py                  Abstract base classes (StructuralTool, HLABindingTool, …)
    registry.py              Tool factory — mock ↔ real selection via env vars
    mock/                    Mock implementations (stage1–4)
    real/
      structural_tool.py     ESMFold (ESM Atlas REST API) — pLDDT + SASA via BioPython
      hla_tool.py            IEDB REST API — Class I (NetMHCpan-4.1) + Class II (NetMHCIIpan-4.0)
    report/
      context.py             Builds LLM context string from PipelineState
      claude_tool.py         Claude (claude-opus-4-6) implementation
      asi1_tool.py           ASI:One stub
      mock_tool.py           Canned scenario-specific reports
  agents/
    nodes.py                 LangGraph node functions + routing logic
    graph.py                 StateGraph definition and compilation
  scoring.py                 Risk aggregation formula

fetch/
  messages.py                Public message contract (PipelineRequest / PipelineResponse)
  pipeline_agent.py          Monolithic uAgent — wraps the full LangGraph pipeline
  client_agent.py            Test client agent (shared by both bureau modes)
  bureau.py                  Monolithic bureau — pipeline agent + client
  bureau_multi.py            Multi-agent bureau — all 7 specialist agents + orchestrator + client
  multi/
    messages.py              Internal inter-agent message schemas (Stage1Request/Response, …)
    session.py               PipelineSession dataclass — orchestrator's per-run state store
    orchestrator.py          Routing agent — replicates LangGraph graph logic as message handlers
    stage1_agent.py          Structural modeling agent (AlphaFold3/ESMFold + SASA)
    stage2_agent.py          HLA antigen presentation agent (NetChop + NetMHCpan)
    stage3_tcr_agent.py      T-cell reactivity agent (NetTCR-2.0)
    stage3_bcell_agent.py    B-cell reactivity agent (DiscoTope-3.0)
    stage4_agent.py          Systems dynamics agent (GenBio AI AIDO)
    report_agent.py          Risk aggregation + LLM clinical summary agent

demo.py                      Rich terminal demo — 4 scenarios
requirements.txt
```
