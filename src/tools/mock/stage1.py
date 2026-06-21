"""
Mock structural tool — simulates AlphaFold3 / ESMFold + SASA calculation.

Scenario dispatch is keyed on PipelineInput.patient_id so the demo can
exercise different pipeline paths without changing graph logic.

  patient_id="HIGH_RISK"      → exposed edit zone, high pLDDT (proceeds normally)
  patient_id="BCELL_AND_SYSTEMS" → buried edit zone, high pLDDT (B-cell epitope + Stage 4 catches RAS/MAPK disruption)
  patient_id="LOW_CONFIDENCE" → first pass returns low pLDDT → triggers retry loop
                                 second pass (fallback_mode=True) returns conservative result
"""

from src.models.pipeline import PipelineInput, StructuralResult
from src.tools.base import StructuralTool


_SCENARIOS: dict[str, StructuralResult] = {
    # Edit sits on a solvent-exposed loop; immune system won't care but
    # the edit disrupts a critical regulatory domain → Stage 4 flags it
    "SYSTEMS_FAILURE": StructuralResult(
        plddt_score=85.1,
        sasa_edit_zone=118.3,   # exposed
        edit_zone_exposed=True,
        confidence="high",
        fallback_mode=False,
    ),
    # Conservative intronic edit — buried residue, high confidence,
    # minimal surface impact, clean transcriptome response
    "BCELL_ONLY": StructuralResult(
        plddt_score=94.2,
        sasa_edit_zone=11.7,    # buried
        edit_zone_exposed=False,
        confidence="high",
        fallback_mode=False,
    ),
    "HIGH_RISK": StructuralResult(
        plddt_score=87.3,
        sasa_edit_zone=142.8,   # Å² — well above 30 Å² buried threshold → exposed
        edit_zone_exposed=True,
        confidence="high",
        fallback_mode=False,
    ),
    "BCELL_AND_SYSTEMS": StructuralResult(
        plddt_score=91.6,
        sasa_edit_zone=18.4,    # buried in hydrophobic core
        edit_zone_exposed=False,
        confidence="high",
        fallback_mode=False,
    ),
    # First-pass result for LOW_CONFIDENCE scenario
    "LOW_CONFIDENCE_FIRST": StructuralResult(
        plddt_score=48.2,       # <50 → low confidence → triggers retry
        sasa_edit_zone=0.0,     # unreliable — disorder region
        edit_zone_exposed=False,
        confidence="low",
        fallback_mode=False,
    ),
    # Fallback result returned on the retry pass
    "LOW_CONFIDENCE_RETRY": StructuralResult(
        plddt_score=48.2,
        sasa_edit_zone=999.0,   # conservative: assume fully exposed when structure uncertain
        edit_zone_exposed=True,
        confidence="low",
        fallback_mode=True,
    ),
}


class MockStructuralTool(StructuralTool):
    def predict(self, inp: PipelineInput, fallback_mode: bool = False) -> StructuralResult:
        pid = inp.patient_id

        if pid == "LOW_CONFIDENCE":
            key = "LOW_CONFIDENCE_RETRY" if fallback_mode else "LOW_CONFIDENCE_FIRST"
            return _SCENARIOS[key]

        return _SCENARIOS[pid]
