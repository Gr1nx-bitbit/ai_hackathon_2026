"""
Inter-agent message schemas for the multi-agent pipeline decomposition.

Every message carries a session_id (UUID) so the orchestrator can correlate
async responses to the correct in-flight pipeline run.

Complex Pydantic models (StructuralResult, HLABindingResult, etc.) are passed
as JSON strings using Pydantic v2's model_dump_json() / model_validate_json().
This avoids double-encoding issues and keeps uagents.Model schemas simple and
registerable on Agentverse without pulling in the full tool dependency tree.

Public API (unchanged):
    PipelineRequest, PipelineResponse — imported from fetch.messages
"""

from typing import Optional
from uagents import Model


# ---------------------------------------------------------------------------
# Stage 1 — Structural modeling
# ---------------------------------------------------------------------------

class Stage1Request(Model):
    session_id: str
    patient_id: str
    sequence: str
    edit_positions: list[int]
    hla_profile: list[str]
    fallback_mode: bool = False


class Stage1Response(Model):
    session_id: str
    structural_json: str    # StructuralResult.model_dump_json()


# ---------------------------------------------------------------------------
# Stage 2 — HLA antigen presentation
# ---------------------------------------------------------------------------

class Stage2Request(Model):
    session_id: str
    input_json: str          # PipelineInput.model_dump_json()
    structural_json: str     # StructuralResult.model_dump_json()


class Stage2Response(Model):
    session_id: str
    hla_binding_json: str    # HLABindingResult.model_dump_json()


# ---------------------------------------------------------------------------
# Stage 3 — T-cell branch
# ---------------------------------------------------------------------------

class Stage3TcrRequest(Model):
    session_id: str
    input_json: str          # PipelineInput.model_dump_json()
    hla_binding_json: str    # HLABindingResult.model_dump_json()


class Stage3TcrResponse(Model):
    session_id: str
    tcr_json: str            # TCRResult.model_dump_json()


# ---------------------------------------------------------------------------
# Stage 3 — B-cell branch
# ---------------------------------------------------------------------------

class Stage3BcellRequest(Model):
    session_id: str
    input_json: str          # PipelineInput.model_dump_json()
    structural_json: str     # StructuralResult.model_dump_json()


class Stage3BcellResponse(Model):
    session_id: str
    bcell_json: str          # BCellResult.model_dump_json()


# ---------------------------------------------------------------------------
# Stage 4 — Systems dynamics
# ---------------------------------------------------------------------------

class Stage4Request(Model):
    session_id: str
    input_json: str          # PipelineInput.model_dump_json()


class Stage4Response(Model):
    session_id: str
    systems_json: str        # SystemsResult.model_dump_json()


# ---------------------------------------------------------------------------
# Report — LLM clinical summary + risk aggregation
# ---------------------------------------------------------------------------

class ReportRequest(Model):
    session_id: str
    pipeline_state_json: str  # JSON-serialised dict of full PipelineState


class ReportResponse(Model):
    session_id: str
    risk_vector_json: str     # RiskVector.model_dump_json()
    clinical_report_json: str  # ClinicalReport.model_dump_json()


# ---------------------------------------------------------------------------
# Error envelope — any specialist agent → orchestrator
# ---------------------------------------------------------------------------

class AgentError(Model):
    session_id: str
    stage: str
    error: str
