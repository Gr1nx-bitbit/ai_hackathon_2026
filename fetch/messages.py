"""
Shared message models for the immunogenicity pipeline uAgent.

Both the pipeline agent and any client agent import from here so the
schema stays in one place. When swapping in a real tool later, only
the pipeline internals change — the message contract stays stable.
"""

from typing import Optional
from uagents import Model


class PipelineRequest(Model):
    """Sent by a client agent to request a pipeline run."""
    patient_id: str
    sequence: str
    edit_positions: list[int]
    hla_profile: list[str]


class PipelineResponse(Model):
    """Returned by the pipeline agent after a run completes."""
    patient_id: str
    recommendation: str          # "safe" | "caution" | "high_risk" | "error"
    overall_risk: float
    structural_risk: float
    immunogenic_risk: float
    reactivity_risk: float
    systems_risk: float
    early_exit_stage: Optional[int] = None
    summary: str
    error: Optional[str] = None
