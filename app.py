"""
Multiscale In Silico Immunogenicity Pipeline — Streamlit Web App

Run:
    uv run streamlit run app.py
"""

import os
import time
from typing import Optional

import streamlit as st

from src.agents.graph import build_graph
from src.models.pipeline import (
    PipelineInput,
    PipelineState,
    RiskVector,
    ClinicalReport,
)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Gene Therapy Safety Screener",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Palette (complements the navy theme in config.toml)
_BG        = "#0f172a"   # deep navy — matches backgroundColor
_BG2       = "#1e293b"   # lighter navy — matches secondaryBackgroundColor
_BG3       = "#0d2137"   # card borders / subtle containers
_ACCENT    = "#4f8ef7"   # slate blue — matches primaryColor
_TEXT_DIM  = "#94a3b8"   # muted slate

_RED    = "#e05c5c"      # high risk
_AMBER  = "#d4924a"      # caution
_TEAL   = "#34b899"      # safe / good signal
_PURPLE = "#7c6af7"      # strong binder
_VIOLET = "#a78bda"      # weak binder

st.markdown(f"""
<style>
    .block-container {{ padding-top: 2rem; }}
    .pill-real {{
        background: #0d2e24; color: {_TEAL}; font-size: 0.72rem;
        padding: 1px 8px; border-radius: 10px; font-weight: 600;
    }}
    .pill-mock {{
        background: {_BG2}; color: {_TEXT_DIM}; font-size: 0.72rem;
        padding: 1px 8px; border-radius: 10px;
    }}
    .pill-avail {{
        background: #2e1f08; color: {_AMBER}; font-size: 0.72rem;
        padding: 1px 8px; border-radius: 10px; font-weight: 600;
    }}
    div[data-testid="metric-container"] {{
        background: {_BG2}; border-radius: 8px; padding: 12px;
        border: 1px solid #2d3f57;
    }}
    div[data-testid="stTabs"] button {{
        font-size: 0.88rem; letter-spacing: 0.02em;
    }}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Preset scenarios
# ---------------------------------------------------------------------------

PRESETS: dict[str, PipelineInput] = {
    "A — High Risk: Immune Rejection": PipelineInput(
        patient_id="HIGH_RISK",
        sequence=(
            "MVLSPADKTNVKAAWGKVGAHAGEYGAEALERMFLSFPTTKTYFPHFDLSHGSAQVKGHGKKVADALTNAVAHVDDMPNAL"
            "SALSDLHAHKLRVDPVNFKLLSHCLLVTLAAHLPAEFTPAVHASLDKFLASVSTVLTSKYR"
        ),
        edit_positions=[47, 48, 49, 50, 51, 52, 53],
        hla_profile=["HLA-A*02:01", "HLA-B*07:02", "HLA-C*07:02", "HLA-DRB1*01:01", "HLA-DQB1*05:01"],
    ),
    "B — B-Cell Epitope + RAS/MAPK Systems Failure": PipelineInput(
        patient_id="BCELL_AND_SYSTEMS",
        sequence=(
            "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQVVIDGETCLLDILDTAGQEEYSAMRDQYMRT"
            "GEGFLCVFAINNTKSFEDIHHQRQEIKRVKDSEDVPMVLVGNKCDLPARTVETRQAQDLARSYGIPYIETSAKTR"
        ),
        edit_positions=[12, 13],
        hla_profile=["HLA-A*01:01", "HLA-B*08:01", "HLA-DRB1*03:01"],
    ),
    "C — Systems Failure: Cellular Disruption": PipelineInput(
        patient_id="SYSTEMS_FAILURE",
        sequence=(
            "MALSLEAPQMAVVSREALVALVQERQKKLAKQEEEDLKKLEKEAEKELRQRQERLKQEREKMLMEQLEKRLQAL"
            "EEAQRREAEHLRRQLTDLQEELMKKLNREAFKQLEEERQLKVELEEMQRREDELRQKLEEELRKAQEELRRTLEDKKE"
        ),
        edit_positions=[22, 23, 24, 25],
        hla_profile=["HLA-A*02:01", "HLA-B*35:01", "HLA-DRB1*04:01"],
    ),
    "D — Stage 3b Flag: B-Cell Epitope Detected, Systems Clear": PipelineInput(
        patient_id="BCELL_ONLY",
        sequence=(
            "MSHHWGYGKHNGPEHWHKDFPIAKGERQSPVDIDTHTAKYDPSLKPLSVSYDQATSLRILNNGAAFNVEFDDSQDKAVL"
            "KGGPLDGTYRLIQFHFHWGSLDGQGSEHTVDKKKYAAELHLVHWNTKYGDFGTAAQQPDGLAVLGIFLKVGSAKPGLQKVVDVLDSIK"
        ),
        edit_positions=[8, 9],
        hla_profile=["HLA-A*03:01", "HLA-B*07:02", "HLA-DRB1*15:01"],
    ),
    "Custom": None,
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@st.cache_resource
def get_pipeline():
    return build_graph()


def _tool_pill(is_real: bool, has_real: bool = False) -> str:
    """
    Three-state pill:
      is_real=True               → green  "real"
      is_real=False, has_real    → amber  "mock / real"  (real impl exists, just not enabled)
      is_real=False, not has_real → grey  "mock"          (no real impl available)
    """
    if is_real:
        return '<span class="pill-real">real</span>'
    if has_real:
        return '<span class="pill-avail">mock / real</span>'
    return '<span class="pill-mock">mock</span>'


def _active_tools() -> dict[str, bool]:
    return {
        "stage1":  os.getenv("ESMFOLD_ENABLED",  "").lower() in ("1", "true"),
        "stage2":  os.getenv("IEDB_ENABLED",      "").lower() in ("1", "true"),
        "stage3b": os.getenv("BEPIPRED_ENABLED",  "").lower() in ("1", "true"),
        "stage4":  False,
        "report":  bool(os.getenv("ASI1_API_KEY") or os.getenv("ANTHROPIC_API_KEY")),
    }


def _report_label() -> str:
    if os.getenv("ASI1_API_KEY"):
        return "ASI:One"
    if os.getenv("ANTHROPIC_API_KEY"):
        return "Claude"
    return "mock"


def _score_color(score: float) -> str:
    if score >= 0.55:
        return _RED
    if score >= 0.25:
        return _AMBER
    return _TEAL


def _risk_bar(score: float, width: int = 160) -> str:
    pct = int(score * 100)
    color = _score_color(score)
    return (
        f'<div style="background:#1e3a5f;border-radius:4px;width:{width}px;height:8px;margin-top:6px;">'
        f'<div style="background:{color};border-radius:4px;width:{pct}%;height:8px;"></div>'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Stage renderers
# ---------------------------------------------------------------------------

def render_stage1(updates: dict) -> None:
    s = updates["structural"]
    conf_color = {"high": "normal", "medium": "off", "low": "inverse"}[s.confidence]
    cols = st.columns([2, 1, 1, 1, 1])
    cols[0].markdown("**Stage 1 — Structural Modeling**")
    cols[1].metric("pLDDT", f"{s.plddt_score:.1f}")
    cols[2].metric("SASA", f"{s.sasa_edit_zone:.1f} Å²")
    cols[3].metric("Exposed", "Yes" if s.edit_zone_exposed else "No")
    conf_label = {"high": f":green[HIGH]", "medium": f":orange[MEDIUM]", "low": f":red[LOW]"}[s.confidence]
    cols[4].markdown(conf_label)
    if s.fallback_mode:
        st.caption("Low structural confidence — fallback mode active (full exposure assumed)")


def render_stage2(updates: dict) -> None:
    h = updates["hla_binding"]
    cols = st.columns([2, 1, 1, 2])
    cols[0].markdown("**Stage 2 — HLA Antigen Presentation**")
    cols[1].metric("Class I %Rank", f"{h.top_class_i_rank:.2f}%")
    cols[2].metric("Class II %Rank", f"{h.top_class_ii_rank:.2f}%")
    has_binders = h.top_class_i_rank < 2.0 or h.top_class_ii_rank < 10.0
    if not has_binders:
        cols[3].success("No significant binders detected")
    else:
        n = len(h.class_i_binders) + len(h.class_ii_binders)
        cols[3].warning(f"{n} binder(s) detected — proceeding to Stage 3")

    if h.class_i_binders and has_binders:
        with st.expander("Top Class I binders"):
            rows = [(b.peptide, b.hla_allele, f"{b.percent_rank:.2f}%", f"{b.ic50_nm:.0f} nM", b.strength)
                    for b in h.class_i_binders[:5]]
            st.table({"Peptide":  [r[0] for r in rows],
                      "Allele":   [r[1] for r in rows],
                      "%Rank":    [r[2] for r in rows],
                      "IC50":     [r[3] for r in rows],
                      "Strength": [r[4] for r in rows]})


def render_stage3_tcr(updates: dict) -> None:
    t = updates["tcr_result"]
    cols = st.columns([2, 2, 1, 1])
    cols[0].markdown("**Stage 3a — T-Cell Reactivity** *(parallel)*")
    cols[1].code(t.peptide, language=None)
    cols[2].metric("TCR prob", f"{t.binding_probability:.2f}")
    if t.above_threshold:
        cols[3].error("Above threshold")
    else:
        cols[3].success("Below threshold")


def render_stage3_bcell(updates: dict) -> None:
    b = updates["bcell_result"]
    cols = st.columns([2, 1, 1, 2])
    cols[0].markdown("**Stage 3b — B-Cell Reactivity** *(parallel)*")
    cols[1].metric("BepiPred", f"{b.bcell_score:.2f}")
    if b.epitope_detected:
        cols[2].error("Epitope detected")
        cols[3].caption(f"Residues: {b.epitope_residues}")
    else:
        cols[2].success("No epitope")


def render_stage3_join(updates: dict) -> None:
    r = updates["reactivity"]
    if r.high_risk_flag:
        st.error("Stage 3 join — High reactivity flag set. Early exit to aggregate.")
    else:
        st.success("Stage 3 join — Reactivity within tolerance. Proceeding to Stage 4.")


def render_stage4(updates: dict) -> None:
    sys = updates["systems"]
    cols = st.columns([2, 1, 1, 2])
    cols[0].markdown("**Stage 4 — Systems Dynamics**")
    cols[1].metric("Stability", f"{sys.overall_stability_score:.2f}")
    toxic = [p.tissue for p in sys.perturbations if p.toxicity_flag]
    if toxic:
        cols[2].error(f"Toxicity: {', '.join(toxic)}")
    else:
        cols[2].success("No toxicity")
    if sys.splice.cryptic_sites_detected:
        cols[3].warning(f"Cryptic splice site detected (dPSI={sys.splice.delta_psi:.2f})")


# ---------------------------------------------------------------------------
# Sequence annotation view
# ---------------------------------------------------------------------------

def render_sequence_view(inp: PipelineInput, hla=None) -> None:
    seq = inp.sequence.replace(" ", "")
    edit_set = set(inp.edit_positions)

    strong_pos: set[int] = set()
    weak_pos:   set[int] = set()
    if hla:
        for b in (hla.class_i_binders + hla.class_ii_binders)[:15]:
            idx = seq.find(b.peptide)
            if idx < 0:
                continue
            span = range(idx, idx + len(b.peptide))
            if b.strength == "strong":
                strong_pos.update(span)
            elif b.strength == "weak":
                weak_pos.update(span)

    LINE = 60
    rows = []
    for start in range(0, len(seq), LINE):
        chunk = seq[start : start + LINE]
        cells = [
            f'<span style="color:{_TEXT_DIM};font-family:monospace;'
            f'font-size:0.75rem;user-select:none;">{start:>4} </span>'
        ]
        for i, aa in enumerate(chunk):
            pos = start + i
            if pos in edit_set:
                s = f"background:{_RED};color:#fff;border-radius:2px;font-weight:700;padding:0 1px;"
            elif pos in strong_pos:
                s = f"background:{_PURPLE};color:#fff;border-radius:2px;padding:0 1px;"
            elif pos in weak_pos:
                s = f"background:{_VIOLET};color:#fff;border-radius:2px;padding:0 1px;"
            else:
                s = f"color:{_TEXT_DIM};"
            cells.append(f'<span style="{s}font-family:monospace;">{aa}</span>')
        rows.append("".join(cells))

    # Legend — only show binder swatches when relevant
    legend_parts = [
        f'<span style="background:{_RED};color:#fff;padding:1px 8px;'
        f'border-radius:4px;font-size:0.8rem;">Edit position</span>',
    ]
    if strong_pos or weak_pos:
        legend_parts += [
            f'<span style="background:{_PURPLE};color:#fff;padding:1px 8px;'
            f'border-radius:4px;font-size:0.8rem;">Strong binder</span>',
            f'<span style="background:{_VIOLET};color:#fff;padding:1px 8px;'
            f'border-radius:4px;font-size:0.8rem;">Weak binder</span>',
        ]
    st.markdown("&nbsp;&nbsp;".join(legend_parts), unsafe_allow_html=True)
    st.markdown("<br>".join(rows), unsafe_allow_html=True)

    caption = f"Sequence length: {len(seq)} aa  ·  Edit positions: {inp.edit_positions}"
    if strong_pos or weak_pos:
        caption += "  ·  Peptide positions mapped from Stage 2 binders"
    elif hla is not None and not (hla.class_i_binders or hla.class_ii_binders):
        caption += "  ·  No HLA binders detected"
    st.caption(caption)


# ---------------------------------------------------------------------------
# Binding affinity chart
# ---------------------------------------------------------------------------

def render_binding_chart(hla) -> None:
    import plotly.graph_objects as go

    class_i  = hla.class_i_binders[:10]
    class_ii = hla.class_ii_binders[:5]
    all_b    = class_i + class_ii

    if not all_b:
        st.info("No binders detected — both HLA class gates passed. Pipeline exited early at Stage 2.")
        return

    _col = {"strong": _RED, "weak": _AMBER, "none": "#334155"}

    def _trace(binders, name):
        labels = [f"{b.peptide}   [{b.hla_allele}]" for b in binders]
        ranks  = [b.percent_rank for b in binders]
        colors = [_col[b.strength] for b in binders]
        hover  = [f"IC50: {b.ic50_nm:.0f} nM  ·  {b.strength} binder" for b in binders]
        return go.Bar(
            name=name,
            x=ranks, y=labels,
            orientation="h",
            marker_color=colors,
            customdata=hover,
            hovertemplate="%{y}<br>%%Rank: %{x:.2f}%%<br>%{customdata}<extra></extra>",
            text=[f"{r:.2f}%" for r in ranks],
            textposition="outside",
            textfont=dict(size=11, color="#e2e8f0"),
        )

    fig = go.Figure()
    if class_i:
        fig.add_trace(_trace(class_i,  "Class I"))
    if class_ii:
        fig.add_trace(_trace(class_ii, "Class II"))

    max_rank = max(b.percent_rank for b in all_b)

    fig.add_vline(x=0.5,  line_dash="dash", line_color=_RED,   line_width=1,
                  annotation_text="Strong (0.5%)",    annotation_font_color=_RED,   annotation_font_size=11)
    fig.add_vline(x=2.0,  line_dash="dash", line_color=_AMBER, line_width=1,
                  annotation_text="Weak (2.0%)",      annotation_font_color=_AMBER, annotation_font_size=11)
    if class_ii:
        fig.add_vline(x=10.0, line_dash="dot", line_color=_ACCENT, line_width=1,
                      annotation_text="Class II gate (10%)", annotation_font_color=_ACCENT, annotation_font_size=11)

    fig.update_layout(
        plot_bgcolor=_BG,
        paper_bgcolor=_BG,
        font_color="#e2e8f0",
        height=max(300, len(all_b) * 48 + 100),
        margin=dict(l=10, r=120, t=50, b=50),
        xaxis=dict(
            title="%Rank  (lower = stronger binder = higher immunogenic risk)",
            gridcolor="#1e3a5f",
            range=[0, min(max_rank * 1.35, 22)],
            tickfont=dict(size=11),
        ),
        yaxis=dict(
            gridcolor="#1e3a5f",
            autorange="reversed",
            tickfont=dict(family="monospace", size=11),
        ),
        legend=dict(bgcolor=_BG, font_color="#e2e8f0"),
        bargap=0.35,
    )

    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        f"Red = strong binder (<0.5% rank)  ·  Amber = weak binder (<2.0%)  ·  "
        "Grey = non-binder  ·  Dashed lines mark clinical thresholds"
    )


# ---------------------------------------------------------------------------
# Risk dashboard
# ---------------------------------------------------------------------------

def render_risk_dashboard(rv: RiskVector) -> None:
    st.divider()
    rec_colors = {"safe": "green", "caution": "orange", "high_risk": "red"}
    rec_labels = {"safe": "SAFE", "caution": "CAUTION", "high_risk": "HIGH RISK"}
    color = rec_colors.get(rv.recommendation, "gray")
    label = rec_labels.get(rv.recommendation, rv.recommendation.upper())

    st.markdown(f"### :{color}[{label}]  —  Overall risk score: **{rv.overall_risk:.3f}**")
    st.caption(rv.summary)

    cols = st.columns(4)
    dims = [
        ("Structural",  rv.structural_risk,  "10% weight"),
        ("Immunogenic", rv.immunogenic_risk,  "35% weight"),
        ("Reactivity",  rv.reactivity_risk,   "35% weight"),
        ("Systems",     rv.systems_risk,      "20% weight"),
    ]
    for col, (name, score, weight) in zip(cols, dims):
        with col:
            st.metric(label=f"{name}  ·  {weight}", value=f"{score:.3f}")
            st.markdown(_risk_bar(score), unsafe_allow_html=True)



# ---------------------------------------------------------------------------
# Clinical report
# ---------------------------------------------------------------------------

def render_clinical_report(report: ClinicalReport) -> None:
    llm = _report_label()
    st.markdown(
        f"### Clinical Report"
        f"<span style='color:{_TEXT_DIM};font-weight:normal;font-size:0.85rem;'>"
        f"  generated by {llm}</span>",
        unsafe_allow_html=True,
    )
    st.markdown(f"**{report.headline}**")

    st.markdown("**Stage Findings**")
    for finding in report.stage_findings:
        st.markdown(f"- {finding}")

    st.markdown("**Risk Rationale**")
    st.markdown(report.risk_rationale)

    if report.mitigation_suggestions:
        st.markdown("**Mitigation Suggestions**")
        for i, sug in enumerate(report.mitigation_suggestions, 1):
            st.markdown(f"{i}. {sug}")

    st.caption(f"*{report.confidence_note}*")


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("## Immunogenicity Pipeline")
    st.caption("In silico safety screening for gene editing therapies")
    st.divider()

    tools = _active_tools()
    st.markdown("**Active tool modes**")
    st.markdown(
        f"Stage 1 — ESMFold &nbsp;&nbsp;&nbsp;&nbsp;&nbsp; {_tool_pill(tools['stage1'], has_real=True)}<br>"
        f"Stage 2 — IEDB &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; {_tool_pill(tools['stage2'], has_real=True)}<br>"
        f"Stage 3a — NetTCR &nbsp;&nbsp;&nbsp;&nbsp;&nbsp; {_tool_pill(False)}<br>"
        f"Stage 3b — BepiPred &nbsp; {_tool_pill(tools['stage3b'], has_real=True)}<br>"
        f"Stage 4 — GenBio AIDO &nbsp; {_tool_pill(False)}<br>"
        f"Report &nbsp;&nbsp;&nbsp;&nbsp; — {_report_label()} &nbsp; {_tool_pill(tools['report'], has_real=True)}",
        unsafe_allow_html=True,
    )
    st.divider()

    st.markdown("**Select scenario**")
    choice = st.selectbox("Scenario", list(PRESETS.keys()), label_visibility="collapsed")

    inp: Optional[PipelineInput] = PRESETS[choice]

    if inp is None:
        st.markdown("**Custom input**")
        custom_seq = st.text_area(
            "Amino acid sequence",
            placeholder="MVLSPADKTNVK...",
            height=100,
        )
        custom_edits = st.text_input(
            "Edit positions (0-indexed, comma-separated)",
            placeholder="47, 48, 49",
        )
        custom_hla = st.text_input(
            "HLA profile (comma-separated)",
            placeholder="HLA-A*02:01, HLA-DRB1*01:01",
        )
        custom_pid = st.text_input("Patient ID", value="CUSTOM")

        if custom_seq and custom_edits and custom_hla:
            try:
                positions = [int(x.strip()) for x in custom_edits.split(",")]
                alleles   = [x.strip() for x in custom_hla.split(",")]
                inp = PipelineInput(
                    patient_id=custom_pid,
                    sequence=custom_seq,
                    edit_positions=positions,
                    hla_profile=alleles,
                )
            except Exception as e:
                st.error(f"Invalid input: {e}")

    st.divider()
    run_button = st.button("Run Pipeline", type="primary", use_container_width=True, disabled=inp is None)


# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------

st.markdown("# Gene Therapy Safety Screener")
st.markdown(
    "Multi-stage, patient-personalised in silico screening for gene editing therapies. "
    "Detects immunogenic rejection risk (HLA presentation, T-cell and B-cell reactivity) "
    "and cell-autonomous systems disruption before a therapy reaches the wet lab. "
    "Powered by a **LangGraph** agentic pipeline, **Fetch AI** multi-agent decomposition, "
    "and **ASI:One** clinical report generation."
)

if not run_button and "result" not in st.session_state:
    # At-a-glance stats row
    st.markdown("<br>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    for col, label, value in [
        (c1, "Pipeline stages",    "4"),
        (c2, "Real bioinformatics tools", "3 available"),
        (c3, "Orchestration",      "LangGraph + Fetch AI"),
        (c4, "Clinical reports",   "ASI:One / Claude"),
    ]:
        with col:
            st.markdown(
                f'<div style="background:{_BG2};border:1px solid #2d3f57;border-radius:8px;'
                f'padding:14px 16px;text-align:center;">'
                f'<div style="font-size:1.3rem;font-weight:700;color:{_ACCENT};">{value}</div>'
                f'<div style="font-size:0.78rem;color:{_TEXT_DIM};margin-top:2px;">{label}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)
    st.info("Select a scenario in the sidebar and click **Run Pipeline** to begin.")

    with st.expander("How it works"):
        st.markdown("""
The pipeline evaluates two independent failure modes for gene therapy edits:

**Immunogenic rejection (Stages 1–3)**
The immune system may recognise the modified protein as foreign. The pipeline checks:
- **Stage 1** — Is the edit zone surface-exposed? (ESMFold structure prediction + SASA)
- **Stage 2** — Do edit-zone peptides bind the patient's HLA alleles? (IEDB / NetMHCpan)
- **Stage 3** — Will those peptides activate T-cells (NetTCR-2.0) or trigger B-cell antibody responses (BepiPred)?

All four stages always run — even an edit with no HLA binders still enters the
gene regulatory network, and Stage 4 may flag systems disruption that immunogenicity
screening alone would miss.

**Systems disruption (Stage 4)**
Even if the immune system tolerates the edit, the cell may not. Stage 4 simulates
transcriptome-level perturbation, cryptic splice sites, and apoptotic signalling.

**Scoring**
A weighted risk vector (structural 10%, immunogenic 35%, reactivity 35%, systems 20%)
produces a final **SAFE / CAUTION / HIGH RISK** recommendation with an LLM-generated
clinical report via ASI:One or Claude.

**Agent architecture**
The pipeline runs as a compiled LangGraph graph locally and as a Fetch AI multi-agent
bureau for agent-to-agent communication. Seven specialist agents (one per stage + an
orchestrator) mirror the LangGraph node structure exactly.
        """)

    st.stop()

# ---------------------------------------------------------------------------
# Run pipeline (streaming)
# ---------------------------------------------------------------------------

if run_button and inp is not None:
    st.session_state.pop("result", None)

    pipeline = get_pipeline()

    initial_state: PipelineState = {
        "input": inp,
        "structural":      None,
        "hla_binding":     None,
        "tcr_result":      None,
        "bcell_result":    None,
        "reactivity":      None,
        "systems":         None,
        "risk_vector":     None,
        "clinical_report": None,
        "retry_count":     0,
    }

    scenario_name = choice if choice != "Custom" else f"Custom — {inp.patient_id}"
    st.markdown(f"## {scenario_name}")
    cols = st.columns(3)
    cols[0].markdown(f"**Patient ID:** `{inp.patient_id}`")
    cols[1].markdown(f"**Edit positions:** `{inp.edit_positions}`")
    cols[2].markdown(f"**HLA alleles:** {len(inp.hla_profile)}")

    st.divider()
    st.markdown("### Pipeline Execution")

    stage_area   = st.container()
    result_state = {**initial_state}

    with st.status("Running pipeline...", expanded=True) as status:
        try:
            t0 = time.monotonic()
            for chunk in pipeline.stream(initial_state, stream_mode="updates"):
                for node_name, updates in chunk.items():
                    elapsed = time.monotonic() - t0
                    result_state.update(updates)

                    with stage_area:
                        with st.container(border=True):
                            if node_name == "stage1":
                                render_stage1(updates)
                                st.caption(f"{elapsed:.1f}s")

                            elif node_name == "increment_retry":
                                st.warning("Low pLDDT detected — retrying in fallback mode")

                            elif node_name == "stage2":
                                render_stage2(updates)
                                st.caption(f"{elapsed:.1f}s")

                            elif node_name == "stage3_tcr":
                                render_stage3_tcr(updates)
                                st.caption(f"{elapsed:.1f}s")

                            elif node_name == "stage3_bcell":
                                render_stage3_bcell(updates)
                                st.caption(f"{elapsed:.1f}s")

                            elif node_name == "stage3_join":
                                render_stage3_join(updates)

                            elif node_name == "stage4":
                                render_stage4(updates)
                                st.caption(f"{elapsed:.1f}s")

            total = time.monotonic() - t0
            status.update(
                label=f"Pipeline complete — {total:.1f}s",
                state="complete",
                expanded=False,
            )
            st.session_state["result"] = result_state

        except Exception as exc:
            import traceback
            status.update(label="Pipeline error", state="error", expanded=True)
            st.error(f"**Pipeline failed:** {exc}")
            with st.expander("Error details"):
                st.code(traceback.format_exc(), language="python")

# ---------------------------------------------------------------------------
# Display stored result (persists across reruns)
# ---------------------------------------------------------------------------

if "result" in st.session_state and not run_button:
    result_state = st.session_state["result"]
    inp = result_state["input"]

    scenario_name = next(
        (k for k, v in PRESETS.items() if v and v.patient_id == inp.patient_id),
        f"Custom — {inp.patient_id}",
    )
    st.markdown(f"## {scenario_name}")
    cols = st.columns(3)
    cols[0].markdown(f"**Patient ID:** `{inp.patient_id}`")
    cols[1].markdown(f"**Edit positions:** `{inp.edit_positions}`")
    cols[2].markdown(f"**HLA alleles:** {len(inp.hla_profile)}")

if "result" in st.session_state:
    result_state = st.session_state["result"]
    rv     = result_state.get("risk_vector")
    report = result_state.get("clinical_report")
    hla    = result_state.get("hla_binding")
    inp    = result_state["input"]

    if rv:
        render_risk_dashboard(rv)

    st.divider()
    tab_binding, tab_sequence, tab_report = st.tabs([
        "Binding Analysis", "Sequence View", "Clinical Report"
    ])

    with tab_binding:
        if hla:
            render_binding_chart(hla)
        else:
            st.info("Stage 2 has not completed yet.")

    with tab_sequence:
        render_sequence_view(inp, hla)

    with tab_report:
        if report:
            render_clinical_report(report)
        else:
            st.info("Clinical report not available.")
