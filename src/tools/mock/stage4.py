"""
Mock Stage 4 tool — simulates GenBio AI AIDO (ModelGenerator).

Covers:
  AIDO.RNA / AIDO.DNA — splice site and isoform stability
  AIDO.Cell           — whole-transcriptome perturbation across target tissues

Scenarios:
  HIGH_RISK / SYSTEMS_FAILURE — severe transcriptome disruption, toxicity_flag=True
  ALL_CLEAR                   — stable transcriptome, minor adaptive stress response only
"""

from src.models.pipeline import (
    PipelineInput,
    SystemsResult,
    SpliceResult,
    PerturbationResult,
)
from src.tools.base import SystemsTool


def _disrupted_result() -> SystemsResult:
    """
    Shared by HIGH_RISK and SYSTEMS_FAILURE.
    SYSTEMS_FAILURE is more severe: cryptic splice site + deeper metabolic collapse.
    """
    splice = SpliceResult(
        cryptic_sites_detected=False,
        affected_transcripts=[],
        delta_psi=0.04,
    )
    liver = PerturbationResult(
        tissue="liver",
        top_upregulated=[
            ("CASP3", 2.14),    # caspase-3: apoptosis effector
            ("TP53",  1.83),    # tumor suppressor activation
            ("BAX",   1.61),    # pro-apoptotic
            ("CDKN1A",1.44),    # p21 — cell cycle arrest
        ],
        top_downregulated=[
            ("BCL2",  -1.92),   # anti-apoptotic suppressed
            ("MYC",   -1.31),
        ],
        housekeeping_stability=0.58,
        toxicity_flag=True,
    )
    hek293 = PerturbationResult(
        tissue="HEK293",
        top_upregulated=[
            ("CASP3", 1.72),
            ("DDIT3", 1.55),    # CHOP — ER stress marker
        ],
        top_downregulated=[
            ("BCL2",  -1.44),
            ("HSPA5", -0.98),   # BiP — ER chaperone
        ],
        housekeeping_stability=0.63,
        toxicity_flag=True,
    )
    stability = (liver.housekeeping_stability + hek293.housekeeping_stability) / 2
    return SystemsResult(
        splice=splice,
        perturbations=[liver, hek293],
        overall_stability_score=round(stability, 3),
    )


def _systems_failure_result() -> SystemsResult:
    """
    Cellular disruption without immune activation — more metabolic than apoptotic.
    Cryptic splice site creates an aberrant isoform; mitochondrial pathway destabilised.
    """
    splice = SpliceResult(
        cryptic_sites_detected=True,
        affected_transcripts=["ENST00000398165.7", "ENST00000361390.5"],
        delta_psi=0.31,         # substantial isoform shift
    )
    liver = PerturbationResult(
        tissue="liver",
        top_upregulated=[
            ("ATF4",  2.61),    # integrated stress response master regulator
            ("DDIT3", 2.44),    # CHOP — ER stress / apoptosis crosstalk
            ("HMOX1", 2.12),    # heme oxygenase-1: oxidative stress marker
            ("SLC7A11",1.88),   # xCT: glutamate/cystine antiporter (ferroptosis)
        ],
        top_downregulated=[
            ("TFAM",  -2.31),   # mitochondrial transcription factor
            ("NDUFB8",-1.97),   # Complex I subunit — electron transport chain
            ("G6PD",  -1.74),   # pentose phosphate pathway — redox balance
        ],
        housekeeping_stability=0.08,    # severely degraded
        toxicity_flag=True,
    )
    hek293 = PerturbationResult(
        tissue="HEK293",
        top_upregulated=[
            ("ATF4",  2.18),
            ("DDIT3", 1.93),
            ("SQSTM1",1.76),    # p62 — autophagy receptor accumulation
        ],
        top_downregulated=[
            ("TFAM",  -2.05),
            ("NDUFB8",-1.83),
            ("ATP5F1B",-1.52),  # ATP synthase subunit
        ],
        housekeeping_stability=0.11,
        toxicity_flag=True,
    )
    stability = (liver.housekeeping_stability + hek293.housekeeping_stability) / 2
    return SystemsResult(
        splice=splice,
        perturbations=[liver, hek293],
        overall_stability_score=round(stability, 3),
    )


def _all_clear_result() -> SystemsResult:
    """
    Edit is well-tolerated. Minor adaptive heat-shock / chaperone upregulation —
    a normal cellular response to any protein sequence change — but no stress
    cascade, no apoptotic signal, stable housekeeping network.
    """
    splice = SpliceResult(
        cryptic_sites_detected=False,
        affected_transcripts=[],
        delta_psi=0.02,
    )
    liver = PerturbationResult(
        tissue="liver",
        top_upregulated=[
            ("HSPA1A", 0.42),   # HSP70 — mild chaperone induction
            ("HSPB1",  0.38),   # HSP27
        ],
        top_downregulated=[],
        housekeeping_stability=0.94,
        toxicity_flag=False,
    )
    hek293 = PerturbationResult(
        tissue="HEK293",
        top_upregulated=[
            ("HSPA1A", 0.39),
            ("DNAJB1", 0.31),   # co-chaperone
        ],
        top_downregulated=[],
        housekeeping_stability=0.92,
        toxicity_flag=False,
    )
    stability = (liver.housekeeping_stability + hek293.housekeeping_stability) / 2
    return SystemsResult(
        splice=splice,
        perturbations=[liver, hek293],
        overall_stability_score=round(stability, 3),
    )


class MockSystemsTool(SystemsTool):
    def predict(self, inp: PipelineInput) -> SystemsResult:
        if inp.patient_id == "SYSTEMS_FAILURE":
            return _systems_failure_result()
        if inp.patient_id == "ALL_CLEAR":
            return _all_clear_result()
        return _disrupted_result()
