"""
Risk aggregation — translates per-stage outputs into a unified RiskVector.

Weights reflect clinical priority: immunogenic and reactivity risk dominate
because T-cell/B-cell recognition is the primary failure mode for gene therapies.

  structural_risk   (10%) — surface exposure increases processing/presentation probability
  immunogenic_risk  (35%) — HLA binding affinity; direct predictor of antigen presentation
  reactivity_risk   (35%) — TCR/BCR recognition; actual immune activation probability
  systems_risk      (20%) — transcriptome stability; secondary but serious safety signal

Thresholds:
  overall < 0.25  → safe
  0.25 ≤ overall < 0.55 → caution
  overall ≥ 0.55  → high_risk
"""

from src.models.pipeline import (
    PipelineState,
    StructuralResult,
    HLABindingResult,
    ReactivityResult,
    SystemsResult,
    RiskVector,
)


def _structural_risk(s: StructuralResult) -> float:
    if s.fallback_mode:
        return 0.6   # conservative: assume worst when structure is uncertain
    if s.edit_zone_exposed:
        return 0.7 if s.plddt_score >= 70 else 0.55
    return 0.15


def _immunogenic_risk(h: HLABindingResult) -> float:
    # Tiered scoring reflects the clinical difference between strong and weak binders.
    # A linear normalisation would conflate them; a weak binder (%Rank ~1.9) is
    # meaningfully less dangerous than a strong binder (%Rank ~0.3).
    #
    # Class I tiers:  strong < 0.5% → 0.90 | weak < 2.0% → 0.40 | none → decays to 0
    # Class II tiers: strong < 2.0% → 0.90 | weak < 10.0% → 0.35 | none → decays to 0

    def _class_i(rank: float) -> float:
        if rank < 0.5:  return 0.90
        if rank < 2.0:  return 0.40
        return max(0.05, 0.30 * (1.0 - rank / 10.0))

    def _class_ii(rank: float) -> float:
        if rank < 2.0:  return 0.90
        if rank < 10.0: return 0.35
        return max(0.05, 0.25 * (1.0 - rank / 20.0))

    return round(0.6 * _class_i(h.top_class_i_rank) + 0.4 * _class_ii(h.top_class_ii_rank), 3)


def _reactivity_risk(r: ReactivityResult) -> float:
    tcr = r.tcr.binding_probability                         # 0–1
    bcell = 1.0 if r.bcell.epitope_detected else 0.2
    return round(0.55 * tcr + 0.45 * bcell, 3)


def _systems_risk(s: SystemsResult) -> float:
    instability = 1.0 - s.overall_stability_score
    toxicity_penalty = 0.3 if any(p.toxicity_flag for p in s.perturbations) else 0.0
    return round(min(1.0, instability + toxicity_penalty), 3)


def compute_risk_vector(state: PipelineState) -> RiskVector:
    s_risk = _structural_risk(state["structural"])

    if state["hla_binding"].early_exit:
        return RiskVector(
            structural_risk=s_risk,
            immunogenic_risk=0.05,
            reactivity_risk=0.0,
            systems_risk=0.0,
            overall_risk=round(0.10 * s_risk + 0.05, 3),
            recommendation="safe",
            early_exit_stage=2,
            summary=(
                "HLA Class I and Class II binding thresholds both indicate negligible "
                "presentation risk. Pipeline exited early at Stage 2. "
                "No T-cell or systems analysis required."
            ),
        )

    i_risk = _immunogenic_risk(state["hla_binding"])

    if state["reactivity"] is not None and state["reactivity"].high_risk_flag and state["systems"] is None:
        r_risk = _reactivity_risk(state["reactivity"])
        overall = round(0.10 * s_risk + 0.35 * i_risk + 0.35 * r_risk + 0.20 * 0.5, 3)
        rec = "high_risk" if overall >= 0.55 else "caution"
        return RiskVector(
            structural_risk=s_risk,
            immunogenic_risk=i_risk,
            reactivity_risk=r_risk,
            systems_risk=0.5,   # unknown — flagged as moderate pending full Stage 4
            overall_risk=overall,
            recommendation=rec,
            early_exit_stage=3,
            summary=(
                f"High T-cell and B-cell reactivity signals detected "
                f"(TCR prob={state['reactivity'].tcr.binding_probability:.2f}, "
                f"BepiPred={state['reactivity'].bcell.bcell_score:.2f}). "
                "Pipeline exited early at Stage 3. Systems analysis skipped."
            ),
        )

    r_risk = _reactivity_risk(state["reactivity"]) if state["reactivity"] else 0.0
    sys_risk = _systems_risk(state["systems"]) if state["systems"] else 0.0

    overall = round(
        0.10 * s_risk
        + 0.35 * i_risk
        + 0.35 * r_risk
        + 0.20 * sys_risk,
        3,
    )

    if overall >= 0.55:
        rec = "high_risk"
    elif overall >= 0.25:
        rec = "caution"
    else:
        rec = "safe"

    systems_note = ""
    if state["systems"]:
        toxic_tissues = [
            p.tissue for p in state["systems"].perturbations if p.toxicity_flag
        ]
        if toxic_tissues:
            systems_note = (
                f" AIDO.Cell flags apoptotic signature in: {', '.join(toxic_tissues)}."
            )

    return RiskVector(
        structural_risk=s_risk,
        immunogenic_risk=i_risk,
        reactivity_risk=r_risk,
        systems_risk=sys_risk,
        overall_risk=overall,
        recommendation=rec,
        early_exit_stage=None,
        summary=(
            f"Full pipeline completed. Overall risk score: {overall:.3f}.{systems_note}"
        ),
    )
