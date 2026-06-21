"""
LangGraph node functions.

Each node:
  1. Reads what it needs from PipelineState
  2. Calls the appropriate tool via the registry (mock or real)
  3. Returns a dict of state keys to update

Routing functions (used in add_conditional_edges) are also defined here.
"""

from __future__ import annotations

from langgraph.types import Send

from src.models.pipeline import PipelineState, ReactivityResult
from src.scoring import compute_risk_vector
from src.tools.registry import (
    get_structural_tool,
    get_hla_tool,
    get_tcr_tool,
    get_bcell_tool,
    get_systems_tool,
    get_report_tool,
)


# ---------------------------------------------------------------------------
# Stage 1 — Structural modeling
# ---------------------------------------------------------------------------

def stage1_node(state: PipelineState) -> dict:
    """
    Runs structural prediction. On a retry pass (retry_count > 0), runs in
    fallback_mode so the tool returns a conservative surface-exposure estimate
    rather than stalling on a disordered region.
    """
    retry_count = state.get("retry_count", 0)
    fallback = retry_count > 0

    result = get_structural_tool().predict(state["input"], fallback_mode=fallback)
    return {"structural": result}


def route_after_stage1(state: PipelineState) -> str:
    """
    Retry once if confidence is low and we haven't retried yet.
    The retry increments retry_count so stage1_node knows to use fallback_mode.
    """
    s = state["structural"]
    retry_count = state.get("retry_count", 0)

    if s.confidence == "low" and retry_count == 0:
        return "increment_retry"

    return "stage2"


def increment_retry_node(state: PipelineState) -> dict:
    """Bumps retry_count before looping back to stage1."""
    return {"retry_count": state.get("retry_count", 0) + 1}


# ---------------------------------------------------------------------------
# Stage 2 — HLA antigen presentation
# ---------------------------------------------------------------------------

def stage2_node(state: PipelineState) -> dict:
    result = get_hla_tool().predict(state["input"], state["structural"])
    return {"hla_binding": result}


def route_after_stage2(state: PipelineState) -> list:
    """Always fan out to both Stage 3 branches in parallel."""
    return [
        Send("stage3_tcr", state),
        Send("stage3_bcell", state),
    ]


# ---------------------------------------------------------------------------
# Stage 3 — Immune reactivity (parallel branches)
# ---------------------------------------------------------------------------

def stage3_tcr_node(state: PipelineState) -> dict:
    result = get_tcr_tool().predict(state["input"], state["hla_binding"])
    return {"tcr_result": result}


def stage3_bcell_node(state: PipelineState) -> dict:
    result = get_bcell_tool().predict(state["input"], state["structural"])
    return {"bcell_result": result}


def stage3_join_node(state: PipelineState) -> dict:
    """Joins TCR and B-cell branch results into a single ReactivityResult."""
    tcr = state["tcr_result"]
    bcell = state["bcell_result"]

    reactivity = ReactivityResult(
        tcr=tcr,
        bcell=bcell,
        max_tcr_probability=tcr.binding_probability,
        high_risk_flag=tcr.above_threshold or bcell.epitope_detected,
    )
    return {"reactivity": reactivity}


# ---------------------------------------------------------------------------
# Stage 4 — Systems dynamics (GenBio AI AIDO)
# ---------------------------------------------------------------------------

def stage4_node(state: PipelineState) -> dict:
    result = get_systems_tool().predict(state["input"])
    return {"systems": result}


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def aggregate_node(state: PipelineState) -> dict:
    risk_vector = compute_risk_vector(state)
    return {"risk_vector": risk_vector}


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def report_node(state: PipelineState) -> dict:
    """
    Calls the configured LLM (Claude, ASI:One, or mock) to generate a
    plain-language clinical safety report from the full pipeline state.
    """
    report = get_report_tool().generate(state)
    return {"clinical_report": report}
