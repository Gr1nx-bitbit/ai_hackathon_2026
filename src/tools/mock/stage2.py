"""
Mock HLA binding tool — values derived from real IEDB predictions
(NetMHCpan-4.1 Class I + NetMHCIIpan-4.0 Class II) on the demo sequences.

Scenarios:
  HIGH_RISK        → strong Class I binder (HLA-C*07:02, %Rank=0.06)
                     + strong HLA-A*02:01 binder → strong immunogenic signal
  BCELL_AND_SYSTEMS → no Class I binders above threshold (%Rank=2.3)
                     + no Class II binders (%Rank=21.0) → pipeline still runs all stages
  SYSTEMS_FAILURE  → strong HLA-B*35:01 Class I binder (%Rank=0.41)
                     + weak Class II (%Rank=9.8)
  BCELL_ONLY       → strong HLA-A*03:01 Class I binder (%Rank=0.47)
                     + no Class II binders (%Rank=19.0)
"""

from src.models.pipeline import (
    PipelineInput,
    StructuralResult,
    HLABindingResult,
    PeptideBinding,
)
from src.tools.base import HLABindingTool

# ---------------------------------------------------------------------------
# HIGH_RISK — hemoglobin beta (HBB), edit zone positions 47–53
# ---------------------------------------------------------------------------

_HIGH_RISK_RESULT = HLABindingResult(
    class_i_binders=[
        PeptideBinding(
            peptide="SFPTTKTYF",
            hla_allele="HLA-C*07:02",
            percent_rank=0.06,
            ic50_nm=5.2,
            strength="strong",
        ),
        PeptideBinding(
            peptide="FDLSHGSAQV",
            hla_allele="HLA-A*02:01",
            percent_rank=0.36,
            ic50_nm=28.1,
            strength="strong",
        ),
        PeptideBinding(
            peptide="LSFPTTKTY",
            hla_allele="HLA-C*07:02",
            percent_rank=0.25,
            ic50_nm=17.6,
            strength="strong",
        ),
    ],
    class_ii_binders=[
        PeptideBinding(
            peptide="FPHFDLSHGSAQVKG",
            hla_allele="HLA-DRB1*01:01",
            percent_rank=14.0,
            ic50_nm=8400.0,
            strength="none",
        ),
    ],
    top_class_i_rank=0.06,
    top_class_ii_rank=14.0,
)

# ---------------------------------------------------------------------------
# BCELL_AND_SYSTEMS — KRAS, edit zone positions 12–13 (G12/G13 hotspot)
# No Class I or Class II binders above threshold. Pipeline still runs all
# stages — even without immune activation, the edit enters the gene
# regulatory network and Stage 4 may flag systems disruption.
# ---------------------------------------------------------------------------

_BCELL_AND_SYSTEMS_RESULT = HLABindingResult(
    class_i_binders=[
        PeptideBinding(
            peptide="MTEYKLVVV",
            hla_allele="HLA-A*01:01",
            percent_rank=2.3,
            ic50_nm=920.0,
            strength="none",
        ),
        PeptideBinding(
            peptide="MTEYKLVVV",
            hla_allele="HLA-B*08:01",
            percent_rank=2.3,
            ic50_nm=920.0,
            strength="none",
        ),
        PeptideBinding(
            peptide="EYKLVVVGA",
            hla_allele="HLA-B*08:01",
            percent_rank=2.9,
            ic50_nm=1280.0,
            strength="none",
        ),
    ],
    class_ii_binders=[
        PeptideBinding(
            peptide="EYKLVVVGAGGVGKS",
            hla_allele="HLA-DRB1*03:01",
            percent_rank=21.0,
            ic50_nm=14800.0,
            strength="none",
        ),
    ],
    top_class_i_rank=2.3,
    top_class_ii_rank=21.0,
)

# ---------------------------------------------------------------------------
# SYSTEMS_FAILURE — coiled-coil protein, edit zone positions 22–25
# ---------------------------------------------------------------------------

_SYSTEMS_FAILURE_RESULT = HLABindingResult(
    class_i_binders=[
        PeptideBinding(
            peptide="MAVVSREAL",
            hla_allele="HLA-B*35:01",
            percent_rank=0.41,
            ic50_nm=32.4,
            strength="strong",
        ),
        PeptideBinding(
            peptide="KLAKQEEEDL",
            hla_allele="HLA-A*02:01",
            percent_rank=1.70,
            ic50_nm=480.0,
            strength="weak",
        ),
    ],
    class_ii_binders=[
        PeptideBinding(
            peptide="SREALVALVQERQKK",
            hla_allele="HLA-DRB1*04:01",
            percent_rank=9.8,
            ic50_nm=4200.0,
            strength="weak",
        ),
    ],
    top_class_i_rank=0.41,
    top_class_ii_rank=9.8,
)

# ---------------------------------------------------------------------------
# BCELL_ONLY — carbonic anhydrase II (CA2), edit zone positions 8–9
# ---------------------------------------------------------------------------

_BCELL_ONLY_RESULT = HLABindingResult(
    class_i_binders=[
        PeptideBinding(
            peptide="MSHHWGYGK",
            hla_allele="HLA-A*03:01",
            percent_rank=0.47,
            ic50_nm=38.3,
            strength="strong",
        ),
        PeptideBinding(
            peptide="GPEHWHKDF",
            hla_allele="HLA-B*07:02",
            percent_rank=1.0,
            ic50_nm=200.0,
            strength="weak",
        ),
    ],
    class_ii_binders=[
        PeptideBinding(
            peptide="NGPEHWHKDFPIAKG",
            hla_allele="HLA-DRB1*15:01",
            percent_rank=19.0,
            ic50_nm=12000.0,
            strength="none",
        ),
    ],
    top_class_i_rank=0.47,
    top_class_ii_rank=19.0,
)


class MockHLABindingTool(HLABindingTool):
    def predict(self, inp: PipelineInput, structural: StructuralResult) -> HLABindingResult:
        if inp.patient_id == "BCELL_AND_SYSTEMS":
            return _BCELL_AND_SYSTEMS_RESULT
        if inp.patient_id == "SYSTEMS_FAILURE":
            return _SYSTEMS_FAILURE_RESULT
        if inp.patient_id == "BCELL_ONLY":
            return _BCELL_ONLY_RESULT
        return _HIGH_RISK_RESULT
