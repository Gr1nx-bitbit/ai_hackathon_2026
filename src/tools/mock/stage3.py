"""
Mock Stage 3 tools — simulates NetTCR-2.0 (T-cell) and BepiPred (B-cell).

These run as parallel branches in the graph. Each returns its own model;
they are joined in the stage3_join node.

Scenarios:
  HIGH_RISK        — TCR prob=0.73 (above threshold), conformational B-cell epitope detected
  BCELL_AND_SYSTEMS — TCR prob=0.28 (below threshold), no B-cell epitope (mock); Stage 4 catches systems disruption
  SYSTEMS_FAILURE   — TCR prob=0.31 (below threshold), no B-cell epitope
  BCELL_ONLY        — TCR prob=0.22 (below threshold), B-cell epitope detected (real BepiPred)
"""

from src.models.pipeline import (
    PipelineInput,
    HLABindingResult,
    StructuralResult,
    TCRResult,
    BCellResult,
)
from src.tools.base import TCRTool, BCellTool

_LOW_REACTIVITY_PIDS = {"BCELL_AND_SYSTEMS", "SYSTEMS_FAILURE", "BCELL_ONLY"}


class MockTCRTool(TCRTool):
    def predict(self, inp: PipelineInput, hla_binding: HLABindingResult) -> TCRResult:
        # Use the top Class I binder as the candidate peptide for TCR scoring.
        # When using a real HLA tool (e.g. IEDB) with no strong/weak binders,
        # class_i_binders may be empty — fall back to a placeholder with
        # minimal TCR activation probability.
        if not hla_binding.class_i_binders:
            return TCRResult(
                peptide="UNKNOWN",
                hla_allele=inp.hla_profile[0] if inp.hla_profile else "HLA-A*02:01",
                binding_probability=0.05,
                above_threshold=False,
            )

        top_binder = hla_binding.class_i_binders[0]

        if inp.patient_id in _LOW_REACTIVITY_PIDS:
            prob = 0.22 if inp.patient_id == "BCELL_ONLY" else (0.28 if inp.patient_id == "BCELL_AND_SYSTEMS" else 0.31)
            return TCRResult(
                peptide=top_binder.peptide,
                hla_allele=top_binder.hla_allele,
                binding_probability=prob,
                above_threshold=False,  # < 0.5 threshold — T-cells won't be activated
            )

        # HIGH_RISK (and any unrecognised patient_id)
        return TCRResult(
            peptide=top_binder.peptide,
            hla_allele=top_binder.hla_allele,
            binding_probability=0.73,
            above_threshold=True,
        )


class MockBCellTool(BCellTool):
    def predict(self, inp: PipelineInput, structural: StructuralResult) -> BCellResult:
        # BepiPred score range ≈ −1 to +1; threshold = 0.35
        if inp.patient_id == "BCELL_AND_SYSTEMS":
            return BCellResult(
                epitope_residues=[],
                bcell_score=0.11,       # KRAS G12/G13 edit zone — below 0.35 threshold
                epitope_detected=False,
            )

        if inp.patient_id == "SYSTEMS_FAILURE":
            return BCellResult(
                epitope_residues=[],
                bcell_score=-0.07,      # real BepiPred value for this sequence/edit
                epitope_detected=False,
            )

        if inp.patient_id == "BCELL_ONLY":
            return BCellResult(
                epitope_residues=[8, 9],
                bcell_score=0.41,       # real BepiPred flags CA2 edit zone
                epitope_detected=True,
            )

        # HIGH_RISK — mean 0.34 over edit zone; segment at residues 51–53 is above
        # the 0.35 threshold, so epitope_detected=True even though the mean is
        # marginally below threshold (illustrates segment-based detection)
        return BCellResult(
            epitope_residues=[51, 52, 53],
            bcell_score=0.34,           # real BepiPred mean for HBB edit zone
            epitope_detected=True,
        )
