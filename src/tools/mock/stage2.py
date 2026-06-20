"""
Mock HLA binding tool — values derived from real IEDB predictions
(NetMHCpan-4.1 Class I + NetMHCIIpan-4.0 Class II) on the demo sequences.

Gate logic (replicated from the real tool contract):
  Early exit ONLY if BOTH thresholds are exceeded:
    Class I:  top %Rank > 2.0  (no strong/weak binders)
    Class II: top %Rank > 10.0 (no binders)

Scenarios:
  HIGH_RISK       → strong Class I binder (HLA-C*07:02, %Rank=0.06)
                    + strong HLA-A*02:01 binder → pipeline proceeds
  EARLY_EXIT      → no Class I binders above threshold (%Rank=2.3)
                    + no Class II binders (%Rank=21.0) → early exit
  SYSTEMS_FAILURE → strong HLA-B*35:01 Class I binder (%Rank=0.41)
                    + weak Class II (%Rank=9.8) → pipeline proceeds
  ALL_CLEAR       → strong HLA-A*03:01 Class I binder (%Rank=0.47)
                    + no Class II binders (%Rank=19.0) → pipeline proceeds
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
# SFPTTKTYF is a strong HLA-C*07:02 9-mer binder; FDLSHGSAQV overlaps the
# edit zone directly and binds HLA-A*02:01.
# ---------------------------------------------------------------------------

_HIGH_RISK_RESULT = HLABindingResult(
    class_i_binders=[
        PeptideBinding(
            peptide="SFPTTKTYF",
            hla_allele="HLA-C*07:02",
            percent_rank=0.06,      # top 0.06% — very strong binder
            ic50_nm=5.2,
            strength="strong",
        ),
        PeptideBinding(
            peptide="FDLSHGSAQV",   # 10-mer directly overlapping edit zone
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
            percent_rank=14.0,      # above 10.0 — no Class II binding
            ic50_nm=8400.0,
            strength="none",
        ),
    ],
    top_class_i_rank=0.06,
    top_class_ii_rank=14.0,
    early_exit=False,  # Class I 0.06 < 2.0 → cannot early exit
)

# ---------------------------------------------------------------------------
# EARLY_EXIT — KRAS, edit zone positions 12–13 (G12/G13 hotspot)
# No Class I binders above 2.0% threshold; no Class II binders above 10.0%.
# ---------------------------------------------------------------------------

_EARLY_EXIT_RESULT = HLABindingResult(
    class_i_binders=[
        PeptideBinding(
            peptide="MTEYKLVVV",
            hla_allele="HLA-A*01:01",
            percent_rank=2.3,       # above 2.0 → non-binder
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
            percent_rank=21.0,      # > 10.0 → non-binder
            ic50_nm=14800.0,
            strength="none",
        ),
    ],
    top_class_i_rank=2.3,    # > 2.0 ✓
    top_class_ii_rank=21.0,  # > 10.0 ✓ → both gates pass → early exit
    early_exit=True,
)

# ---------------------------------------------------------------------------
# SYSTEMS_FAILURE — coiled-coil protein, edit zone positions 22–25
# Strong HLA-B*35:01 Class I binder; weak Class II just under 10.0 threshold.
# TCR and B-cell screening will show no reactivity → Stage 4 runs.
# ---------------------------------------------------------------------------

_SYSTEMS_FAILURE_RESULT = HLABindingResult(
    class_i_binders=[
        PeptideBinding(
            peptide="MAVVSREAL",
            hla_allele="HLA-B*35:01",
            percent_rank=0.41,      # strong binder
            ic50_nm=32.4,
            strength="strong",
        ),
        PeptideBinding(
            peptide="KLAKQEEEDL",
            hla_allele="HLA-A*02:01",
            percent_rank=1.70,      # weak binder
            ic50_nm=480.0,
            strength="weak",
        ),
    ],
    class_ii_binders=[
        PeptideBinding(
            peptide="SREALVALVQERQKK",
            hla_allele="HLA-DRB1*04:01",
            percent_rank=9.8,       # weak Class II — just below 10.0 cutoff
            ic50_nm=4200.0,
            strength="weak",
        ),
    ],
    top_class_i_rank=0.41,
    top_class_ii_rank=9.8,
    early_exit=False,  # Class II 9.8 < 10.0 → cannot early exit
)

# ---------------------------------------------------------------------------
# ALL_CLEAR — carbonic anhydrase II (CA2), edit zone positions 8–9
# Strong sequence-level HLA-A*03:01 binder, but the deeply buried structural
# context reduces actual antigen presentation likelihood. No reactivity at Stage 3.
# ---------------------------------------------------------------------------

_ALL_CLEAR_RESULT = HLABindingResult(
    class_i_binders=[
        PeptideBinding(
            peptide="MSHHWGYGK",
            hla_allele="HLA-A*03:01",
            percent_rank=0.47,      # strong at sequence level
            ic50_nm=38.3,
            strength="strong",
        ),
        PeptideBinding(
            peptide="GPEHWHKDF",
            hla_allele="HLA-B*07:02",
            percent_rank=1.0,       # weak binder
            ic50_nm=200.0,
            strength="weak",
        ),
    ],
    class_ii_binders=[
        PeptideBinding(
            peptide="NGPEHWHKDFPIAKG",
            hla_allele="HLA-DRB1*15:01",
            percent_rank=19.0,      # > 10.0 → non-binder
            ic50_nm=12000.0,
            strength="none",
        ),
    ],
    top_class_i_rank=0.47,
    top_class_ii_rank=19.0,
    early_exit=False,  # Class I 0.47 < 2.0 → cannot early exit
)


class MockHLABindingTool(HLABindingTool):
    def predict(self, inp: PipelineInput, structural: StructuralResult) -> HLABindingResult:
        if inp.patient_id == "EARLY_EXIT":
            return _EARLY_EXIT_RESULT
        if inp.patient_id == "SYSTEMS_FAILURE":
            return _SYSTEMS_FAILURE_RESULT
        if inp.patient_id == "ALL_CLEAR":
            return _ALL_CLEAR_RESULT
        return _HIGH_RISK_RESULT
