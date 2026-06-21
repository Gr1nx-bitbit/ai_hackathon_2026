"""
Mock report tool — returns realistic canned ClinicalReports per scenario.

Used when ANTHROPIC_API_KEY is not set or REPORT_LLM=mock.
The content mirrors what Claude would realistically produce for each scenario.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from src.models.pipeline import ClinicalReport
from src.tools.base import ReportTool

if TYPE_CHECKING:
    from src.models.pipeline import PipelineState

_REPORTS: dict[str, ClinicalReport] = {
    "HIGH_RISK": ClinicalReport(
        headline=(
            "This gene edit poses a HIGH immunogenic risk: strong HLA-C*07:02 and "
            "HLA-A*02:01 binders were confirmed by T-cell and B-cell reactivity analysis "
            "and warrant immediate sequence redesign before any clinical progression."
        ),
        stage_findings=[
            "Stage 1 — Structural: The edited residues (positions 47–53) are fully "
            "surface-exposed (SASA = 142.8 Å²) with high structural confidence (pLDDT = 87.3), "
            "making them directly accessible to immune surveillance machinery.",
            "Stage 2 — HLA Presentation: Two strong Class I binders were identified: "
            "SFPTTKTYF (HLA-C*07:02, IC50 ≈ 5 nM, %Rank = 0.06) placing it in the top "
            "0.06% of all binders for this allele, and FDLSHGSAQV (HLA-A*02:01, IC50 ≈ 28 nM, "
            "%Rank = 0.36) which directly overlaps the edit zone. Efficient CD8⁺ T-cell "
            "priming is predicted.",
            "Stage 3 — Immune Reactivity: NetTCR-2.0 predicted robust TCR binding for the "
            "top binder (probability = 0.73, above 0.5 threshold). BepiPred simultaneously "
            "detected a linear B-cell epitope at edit-zone residues 51–53 (mean score = 0.34; "
            "individual residues exceed the 0.35 threshold). Both arms of adaptive immunity "
            "are activated. Pipeline exited early here.",
        ],
        risk_rationale=(
            "The combination of surface exposure (Stage 1), efficient MHC-I presentation "
            "to both HLA-C*07:02 and HLA-A*02:01 (Stage 2), and confirmed T-cell and B-cell "
            "recognition (Stage 3) constitutes the classical immunogenic triad for a gene "
            "therapy payload. An overall risk score of 0.783 reflects this convergence: the "
            "edit is predicted to trigger CD8⁺ cytotoxic killing of transduced cells and a "
            "neutralising antibody response, likely eliminating therapeutic efficacy and "
            "posing a serious adverse event risk. Systems analysis was skipped as immune "
            "rejection would precede any cellular dysfunction signal."
        ),
        mitigation_suggestions=[
            "Redesign the edit to bury the modified residues: target positions with SASA "
            "< 30 Å², ideally within a hydrophobic core or occluded interface.",
            "Run a silent mutation scan across positions 47–55 to identify synonymous "
            "variants that disrupt the SFPTTKTYF and FDLSHGSAQV epitopes while preserving "
            "protein function — priority on breaking the HLA-C*07:02 anchor residues.",
            "Consider a T-cell tolerisation co-treatment (e.g., rapamycin protocol) if "
            "the edit position cannot be moved without loss of activity.",
            "Validate any redesigned construct with in vitro T-cell proliferation assay "
            "(ELISPOT/ICS) before returning to the pipeline.",
            "Evaluate alternative vector serotypes or tissue-restricted promoters to reduce "
            "antigen expression in APCs.",
        ],
        confidence_note=(
            "Structural prediction used pLDDT and SASA from ESMFold simulation; real values "
            "may differ for disordered or multimeric contexts. NetTCR-2.0 has limited "
            "coverage of non-A*02:01 alleles — validate TCR activation for HLA-C*07:02 with "
            "allele-specific data. In silico binding predictions do not account for "
            "post-translational modifications or proteasomal editing diversity."
        ),
    ),

    "LOW_IMMUNOGENIC": ClinicalReport(
        headline=(
            "This gene edit is predicted CAUTION: the immune system is not expected to "
            "reject the edited cells, but AIDO.Cell detects RAS/MAPK pathway disruption "
            "and a cryptic splice site in the canonical KRAS transcript."
        ),
        stage_findings=[
            "Stage 1 — Structural: The edited residues are buried (SASA = 18.4 Å²) "
            "with very high structural confidence (pLDDT = 91.6). Low surface exposure "
            "limits antigen presentation probability.",
            "Stage 2 — HLA Presentation: No HLA binders were detected across Class I "
            "(top %Rank = 2.3) or Class II (top %Rank = 21.0). The immune system is "
            "unlikely to mount an adaptive response to this edit.",
            "Stage 3 — Immune Reactivity: TCR binding probability 0.28 (below the 0.5 "
            "threshold). No linear B-cell epitopes detected. Consistent with low "
            "immunogenic risk from Stage 2.",
            "Stage 4 — Systems Dynamics: A cryptic splice site was introduced in "
            "ENST00000256078.9 (canonical KRAS transcript), shifting isoform balance "
            "(ΔΨ = 0.19). AIDO.Cell predicts upregulation of MAPK1/RAF1 and loss of "
            "NF1/DUSP6 negative feedback in liver — consistent with constitutive "
            "RAS/MAPK pathway activation. Toxicity flag raised in liver tissue.",
        ],
        risk_rationale=(
            "Despite negligible immunogenic risk, the KRAS G12/G13 edit disrupts a "
            "key oncogenic signalling node. The absence of immune rejection does not "
            "confer safety — the edit still enters the gene regulatory network and "
            "Stage 4 reveals downstream pathway dysregulation that warrants attention "
            "before clinical progression."
        ),
        mitigation_suggestions=[
            "Validate the cryptic splice site experimentally using RT-PCR on "
            "ENST00000256078.9 in the target tissue.",
            "Assess MAPK pathway activation (pERK, pMEK) in edited cells before "
            "advancing to animal studies.",
            "Consider repositioning the edit to avoid the G12/G13 hotspot or use a "
            "base editor to minimise transcriptomic footprint.",
        ],
        confidence_note=(
            "HLA binding predictions are haplotype-specific (HLA-A*01:01, HLA-B*08:01, "
            "HLA-DRB1*03:01). Stage 4 systems predictions are mock — real AIDO.Cell "
            "inference requires the GenBio AI API. Innate immune responses and "
            "vector-related toxicity are not modelled."
        ),
    ),

    "SYSTEMS_FAILURE": ClinicalReport(
        headline=(
            "This gene edit is predicted CAUTION: the immune system is not expected to "
            "reject the edited cells, but AIDO.Cell predicts severe mitochondrial and "
            "metabolic disruption across liver and HEK293 tissues that warrants "
            "functional rescue or edit repositioning."
        ),
        stage_findings=[
            "Stage 1 — Structural: The edited residues are surface-exposed (SASA = 118.3 Å², "
            "pLDDT = 85.1), placing them in the path of antigen-presenting machinery.",
            "Stage 2 — HLA Presentation: A strong HLA-B*35:01 Class I binder was detected "
            "(MAVVSREAL, IC50 ≈ 32 nM, %Rank = 0.41), along with a weak Class II binder "
            "(HLA-DRB1*04:01, %Rank = 9.8). Antigen presentation is structurally possible.",
            "Stage 3 — Immune Reactivity: Despite the strong HLA binder, TCR binding "
            "probability was 0.31 (below the 0.5 activation threshold), suggesting the "
            "patient's TCR repertoire lacks a cognate receptor for this peptide-MHC complex. "
            "BepiPred returned a negative score (−0.07) — no linear B-cell epitope detected. "
            "Immune reactivity is within tolerance.",
            "Stage 4 — Systems Dynamics: This is the critical finding. AIDO.RNA detected a "
            "cryptic splice site (ΔPSI = 0.31) creating an aberrant isoform. AIDO.Cell shows "
            "severe mitochondrial Complex I disruption (TFAM −2.31, NDUFB8 −1.97) and "
            "integrated stress response activation (ATF4 +2.61, DDIT3 +2.44) in both liver "
            "and HEK293, with housekeeping stability collapsed to 0.08–0.11/1.0.",
        ],
        risk_rationale=(
            "The immune system will not reject these edited cells, but the edit disrupts "
            "mitochondrial electron transport chain assembly and triggers a sustained "
            "integrated stress response. The cryptic splice site introduces an aberrant "
            "transcript that likely encodes a truncated or mis-folded protein. "
            "The ATF4/DDIT3/TFAM expression signature is characteristic of proteotoxic "
            "stress leading to apoptosis or ferroptosis — a systems-level toxicity that "
            "would silently eliminate edited cells without an immune signal."
        ),
        mitigation_suggestions=[
            "Eliminate the cryptic splice site: use a splice site prediction tool (SpliceAI, "
            "MaxEntScan) to identify and silent-mutate the GT donor at the flagged position.",
            "Reposition the edit away from the regulatory domain controlling TFAM/NDUFB8 "
            "expression — request a functional domain map from the protein structure team.",
            "Validate mitochondrial membrane potential (JC-1 assay) and ROS production "
            "(MitoSOX) in primary hepatocytes before in vivo dosing.",
            "Consider a smaller edit (base editing or prime editing) that achieves the "
            "therapeutic goal without disrupting the surrounding regulatory context.",
        ],
        confidence_note=(
            "AIDO.Cell perturbation predictions are based on foundation model inference "
            "and carry higher uncertainty than binding affinity predictions. The cryptic "
            "splice site finding is the most actionable signal — validate experimentally "
            "with RT-PCR across the affected locus before committing to redesign. "
            "Transcriptome predictions do not account for compensatory responses that "
            "may emerge over longer timescales in vivo."
        ),
    ),

    "ALL_CLEAR": ClinicalReport(
        headline=(
            "This gene edit is predicted SAFE across all four pipeline stages: "
            "weak HLA binding, no T-cell or B-cell reactivity, and a stable "
            "transcriptome with only minor adaptive heat-shock responses."
        ),
        stage_findings=[
            "Stage 1 — Structural: The edited residues are deeply buried (SASA = 11.7 Å², "
            "pLDDT = 94.2), indicating minimal surface exposure and low likelihood of "
            "proteasomal processing into immunogenic peptides.",
            "Stage 2 — HLA Presentation: A strong sequence-level HLA-A*03:01 binder was "
            "detected (MSHHWGYGK, IC50 ≈ 38 nM, %Rank = 0.47). However, the deeply buried "
            "structural context (SASA = 11.7 Å²) substantially limits proteasomal processing "
            "and MHC-I loading. No Class II binders were detected (top %Rank = 19.0). The "
            "pipeline continued to Stage 3.",
            "Stage 3 — Immune Reactivity: TCR binding probability was 0.22 (well below the "
            "0.5 threshold). BepiPred returned a negative score (−0.12) — no linear B-cell "
            "epitope detected. The immune system is not predicted to mount an adaptive response.",
            "Stage 4 — Systems Dynamics: Transcriptome is stable (overall score 0.93/1.0). "
            "A minor HSP70/HSP27 chaperone induction was observed (log2FC ≈ 0.4), consistent "
            "with a normal cellular adaptation to any protein sequence change. No apoptotic, "
            "stress cascade, or splice disruption signals detected.",
        ],
        risk_rationale=(
            "No stage flagged a clinically significant safety signal. The buried edit position "
            "limits immune surveillance access, the weak HLA binders do not reach activation "
            "thresholds, and the cellular response is limited to a transient chaperone "
            "upregulation — a normal protein quality control response. An overall risk score "
            "of 0.236 places this edit in the SAFE range with margin."
        ),
        mitigation_suggestions=[],
        confidence_note=(
            "A SAFE in silico result does not eliminate the need for in vitro validation. "
            "Recommend a standard immunogenicity panel: PBMC stimulation with the edited "
            "peptides, IFN-γ ELISPOT, and flow cytometry for T-cell activation markers. "
            "Innate responses (TLR signalling, complement activation by the vector) are "
            "outside the scope of this pipeline. Patient-specific validation against the "
            "complete HLA panel is warranted before Phase I."
        ),
    ),
}

_DEFAULT_REPORT = ClinicalReport(
    headline="Pipeline completed — see risk vector for quantitative results.",
    stage_findings=["Full stage detail available in the pipeline state."],
    risk_rationale="No scenario-specific mock report available for this patient_id.",
    mitigation_suggestions=[],
    confidence_note="This is a mock report. Set ANTHROPIC_API_KEY to generate a real Claude report.",
)


class MockReportTool(ReportTool):
    def generate(self, state: "PipelineState") -> ClinicalReport:
        pid = state["input"].patient_id
        return _REPORTS.get(pid, _DEFAULT_REPORT)
