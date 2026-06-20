"""
LangGraph StateGraph definition.

Graph topology:
                        START
                          │
                       stage1
                          │
              ┌─── low confidence ───┐
              │                      │
       increment_retry            stage2
              │                      │
           stage1         ┌── early exit ──┐
                          │                │
                   [stage3_tcr]      aggregate ◄── END (early)
                   [stage3_bcell]
                          │
                    stage3_join
                          │
               ┌── high risk ───┐
               │                │
            stage4         aggregate ◄── END (early)
               │
           aggregate
               │
              END
"""

from langgraph.graph import StateGraph, START, END

from src.models.pipeline import PipelineState
from src.agents.nodes import (
    stage1_node,
    route_after_stage1,
    increment_retry_node,
    stage2_node,
    route_after_stage2,
    stage3_tcr_node,
    stage3_bcell_node,
    stage3_join_node,
    route_after_stage3,
    stage4_node,
    aggregate_node,
    report_node,
)


def build_graph():
    graph = StateGraph(PipelineState)

    # --- Nodes ---
    graph.add_node("stage1", stage1_node)
    graph.add_node("increment_retry", increment_retry_node)
    graph.add_node("stage2", stage2_node)
    graph.add_node("stage3_tcr", stage3_tcr_node)
    graph.add_node("stage3_bcell", stage3_bcell_node)
    graph.add_node("stage3_join", stage3_join_node)
    graph.add_node("stage4", stage4_node)
    graph.add_node("aggregate", aggregate_node)
    graph.add_node("report", report_node)

    # --- Entry ---
    graph.add_edge(START, "stage1")

    # --- Stage 1 → retry loop or stage 2 ---
    graph.add_conditional_edges(
        "stage1",
        route_after_stage1,
        {"increment_retry": "increment_retry", "stage2": "stage2"},
    )
    graph.add_edge("increment_retry", "stage1")   # cyclic: retry once

    # --- Stage 2 → early exit or parallel Stage 3 ---
    graph.add_conditional_edges(
        "stage2",
        route_after_stage2,
        ["aggregate", "stage3_tcr", "stage3_bcell"],  # possible targets for Send
    )

    # --- Stage 3 parallel branches → join ---
    graph.add_edge("stage3_tcr", "stage3_join")
    graph.add_edge("stage3_bcell", "stage3_join")

    # --- Stage 3 join → early exit or Stage 4 ---
    graph.add_conditional_edges(
        "stage3_join",
        route_after_stage3,
        {"aggregate": "aggregate", "stage4": "stage4"},
    )

    # --- Stage 4 → aggregate ---
    graph.add_edge("stage4", "aggregate")

    # --- Aggregate → report → END ---
    graph.add_edge("aggregate", "report")
    graph.add_edge("report", END)

    return graph.compile()
