# Multiscale In Silico Immunogenicity Pipeline

A patient-specific, multi-stage safety screening system for gene editing therapies. Given an edited protein sequence and a patient's HLA profile, the pipeline evaluates two independent failure modes before a therapy reaches the clinic:

1. **Immunogenic rejection** — will the immune system destroy the edited cells?
2. **Systems-level disruption** — will the edit destabilise cellular function even if the immune system tolerates it?

The pipeline is built on **LangGraph** (state machine), wrapped as a **Fetch AI uAgent** (network transport), and capped with an **LLM report node** (Claude or ASI:One) that translates raw scores into a plain-language clinical summary.

---

## Quick Links

| Document | What's inside |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Graph topology, all 5 stages, risk scoring formula, LLM report node, Fetch AI integration, mock/real swap pattern |
| [PROBLEM.md](PROBLEM.md) | The clinical problem, what this POC demonstrates, and what's blocking productionisation |
| [SETUP.md](SETUP.md) | Installation, environment variables, running the demo, Agentverse registration |

---

## 30-Second Overview

```
[Edited sequence + patient HLA profile]
            │
            ▼
      Stage 1 — Structural (AlphaFold3 / ESMFold + SASA)
            │  low pLDDT → retry once in fallback mode
            ▼
      Stage 2 — HLA Presentation (NetChop + NetMHCpan)
            │  both gates pass → early exit (safe)
            ▼
  ┌── Stage 3a — T-cell (NetTCR-2.0) ─────────────────┐
  └── Stage 3b — B-cell (DiscoTope-3.0) ───────────────┘
            │  either flags → early exit (high_risk)
            ▼
      Stage 4 — Systems Dynamics (GenBio AI AIDO)
            │
            ▼
      Aggregate → weighted risk vector (structural / immunogenic / reactivity / systems)
            │
            ▼
      Report → LLM clinical summary (Claude / ASI:One / mock)
```

**Four demo scenarios** illustrate different routing paths: full pipeline with high-risk result, early exit at Stage 2, cellular disruption with immune tolerance, and a clean all-clear.

---

## Stack

| Layer | Technology |
|---|---|
| Workflow orchestration | LangGraph `StateGraph` |
| Data models | Pydantic v2 |
| Agent network | Fetch AI uagents 0.25+ |
| LLM report | Claude `claude-opus-4-6` (adaptive thinking) |
| Terminal demo | Rich |
| All biology tools | Mocked (drop-in ABC interface for real tools) |

---

## Two Fetch AI Deployment Modes

**Monolithic** — one uAgent wraps the full LangGraph pipeline. Simple to register on Agentverse.

**Multi-agent** — each pipeline stage is an independent specialist agent connected via an orchestrator. Any stage can be called directly by other agents on the Agentverse network without running the full pipeline.

Both expose the same `PipelineRequest` / `PipelineResponse` message contract.

---

## Running It

```bash
uv sync

# LangGraph terminal demo (4 scenarios, no Fetch AI)
uv run python demo.py

# Monolithic Fetch AI bureau (pipeline agent + test client)
uv run python -m fetch.bureau

# Multi-agent Fetch AI bureau (7 specialist agents + orchestrator + client)
uv run python -m fetch.bureau_multi
```

Full setup instructions, environment variables, and Agentverse registration steps are in [SETUP.md](SETUP.md).
