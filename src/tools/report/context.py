"""
Builds a structured plain-text context string from the full PipelineState.
Passed as the user message to whichever LLM generates the clinical report.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.models.pipeline import PipelineState


def build_pipeline_context(state: "PipelineState") -> str:
    inp = state["input"]
    rv = state["risk_vector"]

    lines = [
        "GENE THERAPY SAFETY SCREENING — IN SILICO PIPELINE RESULTS",
        f"Patient ID       : {inp.patient_id}",
        f"Sequence length  : {len(inp.sequence)} residues",
        f"Edit positions   : {inp.edit_positions} (0-indexed)",
        f"HLA profile      : {', '.join(inp.hla_profile)}",
        "",
        "=== OVERALL VERDICT ===",
        f"Recommendation   : {rv.recommendation.upper()}",
        f"Overall risk score: {rv.overall_risk:.3f}  (0 = fully safe, 1 = maximum risk)",
    ]

    lines += [
        "",
        "=== RISK DIMENSIONS ===",
        f"  Structural  (weight 10%): {rv.structural_risk:.3f}",
        f"  Immunogenic (weight 35%): {rv.immunogenic_risk:.3f}",
        f"  Reactivity  (weight 35%): {rv.reactivity_risk:.3f}",
        f"  Systems     (weight 20%): {rv.systems_risk:.3f}",
    ]

    if s := state.get("structural"):
        conf_label = "high" if s.plddt_score >= 70 else ("medium" if s.plddt_score >= 50 else "low")
        lines += [
            "",
            "=== STAGE 1: STRUCTURAL ANALYSIS (AlphaFold3/ESMFold + SASA) ===",
            f"  pLDDT confidence score : {s.plddt_score:.1f}/100 ({conf_label} confidence)",
            f"  Edit zone SASA         : {s.sasa_edit_zone:.1f} Å²  (>30 Å² = surface-exposed)",
            f"  Edit zone exposed      : {s.edit_zone_exposed}",
            f"  Fallback mode (low-confidence retry): {s.fallback_mode}",
        ]

    if h := state.get("hla_binding"):
        lines += [
            "",
            "=== STAGE 2: HLA ANTIGEN PRESENTATION (NetChop-3.1 + NetMHCpan-4.1) ===",
            f"  Top Class I  %Rank: {h.top_class_i_rank:.2f}%  (strong binder ≤0.5%, weak ≤2.0%)",
            f"  Top Class II %Rank: {h.top_class_ii_rank:.2f}%  (strong binder ≤2.0%, weak ≤10.0%)",
        ]
        if h.class_i_binders:
            t = h.class_i_binders[0]
            lines.append(
                f"  Best Class I binder   : {t.peptide}  allele={t.hla_allele}  "
                f"IC50={t.ic50_nm:.0f} nM  strength={t.strength}"
            )
        if h.class_ii_binders:
            t = h.class_ii_binders[0]
            lines.append(
                f"  Best Class II binder  : {t.peptide}  allele={t.hla_allele}  "
                f"IC50={t.ic50_nm:.0f} nM  strength={t.strength}"
            )

    if r := state.get("reactivity"):
        lines += [
            "",
            "=== STAGE 3: IMMUNE REACTIVITY (NetTCR-2.0 || BepiPred, parallel) ===",
            f"  T-cell branch:",
            f"    Peptide              : {r.tcr.peptide}",
            f"    HLA allele           : {r.tcr.hla_allele}",
            f"    TCR binding probability: {r.tcr.binding_probability:.2f}  "
            f"({'ABOVE' if r.tcr.above_threshold else 'below'} 0.5 threshold)",
            f"  B-cell branch (BepiPred linear epitope):",
            f"    BepiPred score   : {r.bcell.bcell_score:.2f}  (epitope threshold: 0.35; range ≈ −1 to +1)",
            f"    Linear epitope detected: {r.bcell.epitope_detected}",
            f"    Flagged residues     : {r.bcell.epitope_residues if r.bcell.epitope_residues else 'none'}",
            f"  High reactivity risk flag: {r.high_risk_flag}",
        ]

    if sys := state.get("systems"):
        lines += [
            "",
            "=== STAGE 4: SYSTEMS DYNAMICS (GenBio AI AIDO — RNA/DNA/Cell) ===",
            f"  Cryptic splice sites detected : {sys.splice.cryptic_sites_detected}",
            f"  Delta PSI (isoform shift)     : {sys.splice.delta_psi:.2f}",
        ]
        if sys.splice.affected_transcripts:
            lines.append(f"  Affected transcripts          : {', '.join(sys.splice.affected_transcripts)}")
        lines.append(f"  Overall transcriptome stability: {sys.overall_stability_score:.3f}/1.0")
        for p in sys.perturbations:
            up = ", ".join(f"{g}({fc:+.2f})" for g, fc in p.top_upregulated[:4])
            dn = ", ".join(f"{g}({fc:+.2f})" for g, fc in p.top_downregulated[:3]) or "none"
            lines += [
                f"  Tissue: {p.tissue}",
                f"    Housekeeping stability : {p.housekeeping_stability:.2f}/1.0",
                f"    Toxicity flag          : {p.toxicity_flag}",
                f"    Top upregulated genes  : {up}",
                f"    Top downregulated genes: {dn}",
            ]

    return "\n".join(lines)
