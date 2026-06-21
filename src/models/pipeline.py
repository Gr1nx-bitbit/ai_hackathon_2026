"""
Pydantic schemas for the immunogenicity pipeline.

Every tool in the pipeline — mock or real — communicates through these models.
Swapping a mock for a real binary means returning the same model from a different
implementation; the graph never needs to change.
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


# ---------------------------------------------------------------------------
# Pipeline input
# ---------------------------------------------------------------------------

class PipelineInput(BaseModel):
    patient_id: str
    sequence: str = Field(..., description="Full amino acid sequence of the edited protein")
    edit_positions: list[int] = Field(..., description="0-indexed residue positions that were modified")
    hla_profile: list[str] = Field(
        ...,
        description="Patient HLA alleles, e.g. ['HLA-A*02:01', 'HLA-B*07:02', 'HLA-DRB1*01:01']",
    )


# ---------------------------------------------------------------------------
# Stage 1 — Structural modeling
# ---------------------------------------------------------------------------

class StructuralResult(BaseModel):
    plddt_score: float = Field(..., description="Mean pLDDT confidence (0–100) over edit zone")
    sasa_edit_zone: float = Field(..., description="Mean SASA (Å²) of edited residues; >30 = exposed")
    edit_zone_exposed: bool = Field(..., description="True if edit residues are surface-accessible")
    confidence: Literal["high", "medium", "low"] = Field(
        ..., description="high ≥70 pLDDT, medium ≥50, low <50"
    )
    # Set to True on the retry pass to flag downstream stages
    fallback_mode: bool = False


# ---------------------------------------------------------------------------
# Stage 2 — HLA antigen presentation
# ---------------------------------------------------------------------------

class PeptideBinding(BaseModel):
    peptide: str
    hla_allele: str
    percent_rank: float = Field(..., description="%Rank from NetMHCpan; lower = stronger binder")
    ic50_nm: float = Field(..., description="Predicted IC50 in nM")
    strength: Literal["strong", "weak", "none"]


class HLABindingResult(BaseModel):
    class_i_binders: list[PeptideBinding]
    class_ii_binders: list[PeptideBinding]
    top_class_i_rank: float
    top_class_ii_rank: float


# ---------------------------------------------------------------------------
# Stage 3 — Immune reactivity (parallel T-cell / B-cell branches)
# ---------------------------------------------------------------------------

class TCRResult(BaseModel):
    """Output of the T-cell branch (NetTCR-2.0)."""
    peptide: str
    hla_allele: str
    binding_probability: float = Field(..., ge=0.0, le=1.0)
    above_threshold: bool  # probability > 0.5


class BCellResult(BaseModel):
    """Output of the B-cell branch (BepiPred / linear epitope prediction)."""
    epitope_residues: list[int]
    bcell_score: float = Field(..., description="Mean BepiPred score over edit zone (range ≈ −1 to +1); >0.35 = predicted epitope")
    epitope_detected: bool


class ReactivityResult(BaseModel):
    """Joined result after both Stage 3 branches complete."""
    tcr: TCRResult
    bcell: BCellResult
    max_tcr_probability: float
    high_risk_flag: bool


# ---------------------------------------------------------------------------
# Stage 4 — Systems dynamics (GenBio AI AIDO)
# ---------------------------------------------------------------------------

class SpliceResult(BaseModel):
    """AIDO.RNA / AIDO.DNA output."""
    cryptic_sites_detected: bool
    affected_transcripts: list[str]
    delta_psi: float = Field(..., description="Predicted change in splice-site usage (0–1)")


class PerturbationResult(BaseModel):
    """AIDO.Cell whole-transcriptome perturbation for one tissue."""
    tissue: str
    top_upregulated: list[tuple[str, float]] = Field(
        ..., description="[(gene_symbol, log2FC), ...] for top upregulated genes"
    )
    top_downregulated: list[tuple[str, float]]
    housekeeping_stability: float = Field(..., ge=0.0, le=1.0, description="1 = fully stable")
    toxicity_flag: bool = Field(
        ..., description="True if critical apoptotic/tumor-suppressor genes are dysregulated"
    )


class SystemsResult(BaseModel):
    splice: SpliceResult
    perturbations: list[PerturbationResult]
    overall_stability_score: float = Field(..., ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Final risk aggregation
# ---------------------------------------------------------------------------

class RiskVector(BaseModel):
    structural_risk: float = Field(..., ge=0.0, le=1.0)
    immunogenic_risk: float = Field(..., ge=0.0, le=1.0)
    reactivity_risk: float = Field(..., ge=0.0, le=1.0)
    systems_risk: float = Field(..., ge=0.0, le=1.0)
    overall_risk: float = Field(..., ge=0.0, le=1.0)
    recommendation: Literal["safe", "caution", "high_risk"]
    summary: str


# ---------------------------------------------------------------------------
# Clinical report (generated by the LLM report node)
# ---------------------------------------------------------------------------

class ClinicalReport(BaseModel):
    headline: str = Field(..., description="One-sentence safety verdict for the treating physician")
    stage_findings: list[str] = Field(
        ...,
        description="Plain-language finding per pipeline stage that ran, in stage order",
    )
    risk_rationale: str = Field(
        ...,
        description="2-3 sentence explanation of the overall risk score and dominant mechanisms",
    )
    mitigation_suggestions: list[str] = Field(
        ...,
        description="Actionable next steps; empty list when recommendation is 'safe'",
    )
    confidence_note: str = Field(
        ...,
        description="Caveats about prediction confidence, tool limitations, or in silico vs. in vivo gap",
    )


# ---------------------------------------------------------------------------
# LangGraph pipeline state
# ---------------------------------------------------------------------------

class PipelineState(TypedDict):
    input: PipelineInput

    # Stage outputs — None until the stage runs
    structural: Optional[StructuralResult]
    hla_binding: Optional[HLABindingResult]

    # Stage 3 written independently by parallel branches, joined in stage3_join
    tcr_result: Optional[TCRResult]
    bcell_result: Optional[BCellResult]
    reactivity: Optional[ReactivityResult]

    systems: Optional[SystemsResult]
    risk_vector: Optional[RiskVector]
    clinical_report: Optional[ClinicalReport]

    # Retry bookkeeping for the structural confidence loop
    retry_count: int
