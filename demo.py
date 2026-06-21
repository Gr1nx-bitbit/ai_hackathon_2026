"""
Immunogenicity Pipeline — POC Demo

Runs two scenarios to demonstrate the agentic routing logic:

  Scenario A: HIGH_RISK        — full pipeline, strong immune response, high-risk result
  Scenario B: BCELL_AND_SYSTEMS — B-cell epitope detected + Stage 4 catches RAS/MAPK disruption
  Scenario D: BCELL_ONLY       — Stage 3b B-cell epitope detected, systems clear

Run:
    python demo.py
"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box
from rich.markdown import Markdown

from src.agents.graph import build_graph
from src.models.pipeline import PipelineInput, PipelineState, RiskVector, ClinicalReport

console = Console()

# ---------------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------------

SCENARIOS: list[PipelineInput] = [
    PipelineInput(
        patient_id="HIGH_RISK",
        sequence=(
            "MVLSPADKTNVKAAWGKVGAHAGEYGAEALERMFLSFPTTKTYFPHFDLSHGSAQVKGHGKKVADALTNAVAHVDDMPNAL"
            "SALSDLHAHKLRVDPVNFKLLSHCLLVTLAAHLPAEFTPAVHASLDKFLASVSTVLTSKYR"
        ),
        edit_positions=[47, 48, 49, 50, 51, 52, 53],
        hla_profile=["HLA-A*02:01", "HLA-B*07:02", "HLA-C*07:02", "HLA-DRB1*01:01", "HLA-DQB1*05:01"],
    ),
    PipelineInput(
        patient_id="BCELL_AND_SYSTEMS",
        sequence=(
            "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQVVIDGETCLLDILDTAGQEEYSAMRDQYMRT"
            "GEGFLCVFAINNTKSFEDIHHQRQEIKRVKDSEDVPMVLVGNKCDLPARTVETRQAQDLARSYGIPYIETSAKTR"
        ),
        edit_positions=[12, 13],
        hla_profile=["HLA-A*01:01", "HLA-B*08:01", "HLA-DRB1*03:01"],
    ),
    PipelineInput(
        patient_id="SYSTEMS_FAILURE",
        sequence=(
            "MALSLEAPQMAVVSREALVALVQERQKKLAKQEEEDLKKLEKEAEKELRQRQERLKQEREKMLMEQLEKRLQAL"
            "EEAQRREAEHLRRQLTDLQEELMKKLNREAFKQLEEERQLKVELEEMQRREDELRQKLEEELRKAQEELRRTLEDKKE"
        ),
        edit_positions=[22, 23, 24, 25],
        hla_profile=["HLA-A*02:01", "HLA-B*35:01", "HLA-DRB1*04:01"],
    ),
    PipelineInput(
        patient_id="BCELL_ONLY",
        sequence=(
            "MSHHWGYGKHNGPEHWHKDFPIAKGERQSPVDIDTHTAKYDPSLKPLSVSYDQATSLRILNNGAAFNVEFDDSQDKAVL"
            "KGGPLDGTYRLIQFHFHWGSLDGQGSEHTVDKKKYAAELHLVHWNTKYGDFGTAAQQPDGLAVLGIFLKVGSAKPGLQKVVDVLDSIK"
        ),
        edit_positions=[8, 9],
        hla_profile=["HLA-A*03:01", "HLA-B*07:02", "HLA-DRB1*15:01"],
    ),
]

SCENARIO_LABELS = {
    "HIGH_RISK":       "Scenario A — Immune Rejection Risk (Full Pipeline)",
    "BCELL_AND_SYSTEMS": "Scenario B — B-Cell Epitope + RAS/MAPK Systems Failure",
    "SYSTEMS_FAILURE":   "Scenario C — Cellular Disruption (Immune System Tolerates, Cell Does Not)",
    "BCELL_ONLY":        "Scenario D — Stage 3b Flag: B-Cell Epitope Detected, Systems Clear",
}


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _risk_color(score: float) -> str:
    if score >= 0.55:
        return "bold red"
    if score >= 0.25:
        return "bold yellow"
    return "bold green"


def _recommendation_badge(rec: str) -> Text:
    styles = {
        "safe": ("SAFE", "bold white on green"),
        "caution": ("CAUTION", "bold black on yellow"),
        "high_risk": ("HIGH RISK", "bold white on red"),
    }
    label, style = styles.get(rec, ("UNKNOWN", "bold"))
    return Text(f" {label} ", style=style)


def print_stage_header(stage: str, detail: str = "") -> None:
    console.print(f"\n  [dim]▸[/dim] [bold cyan]{stage}[/bold cyan]" + (f"  [dim]{detail}[/dim]" if detail else ""))


def print_clinical_report(report: ClinicalReport) -> None:
    import os
    llm_label = (
        "claude-opus-4-6"
        if os.getenv("ANTHROPIC_API_KEY") and os.getenv("REPORT_LLM", "auto") != "mock"
        else "mock"
    )
    console.print(
        Panel(
            f"[bold]{report.headline}[/bold]",
            title=f"[cyan]Clinical Report[/cyan]  [dim]({llm_label})[/dim]",
            border_style="cyan",
        )
    )

    console.print("\n  [bold]Stage Findings[/bold]")
    for finding in report.stage_findings:
        console.print(f"  [dim]•[/dim] {finding}\n")

    console.print(f"  [bold]Risk Rationale[/bold]\n  {report.risk_rationale}\n")

    if report.mitigation_suggestions:
        console.print("  [bold]Mitigation Suggestions[/bold]")
        for i, sug in enumerate(report.mitigation_suggestions, 1):
            console.print(f"  [yellow]{i}.[/yellow] {sug}\n")

    console.print(f"  [dim]Confidence note: {report.confidence_note}[/dim]\n")


def print_risk_vector(rv: RiskVector) -> None:
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold white")
    table.add_column("Dimension", style="cyan", width=22)
    table.add_column("Score", justify="right", width=8)
    table.add_column("Bar", width=30)

    dimensions = [
        ("Structural",    rv.structural_risk),
        ("Immunogenic",   rv.immunogenic_risk),
        ("Reactivity",    rv.reactivity_risk),
        ("Systems",       rv.systems_risk),
        ("─" * 20, None),
        ("Overall",       rv.overall_risk),
    ]

    for name, score in dimensions:
        if score is None:
            table.add_row(f"[dim]{name}[/dim]", "", "")
            continue
        bar_len = int(score * 28)
        bar = "█" * bar_len + "░" * (28 - bar_len)
        color = _risk_color(score)
        table.add_row(name, f"[{color}]{score:.3f}[/{color}]", f"[{color}]{bar}[/{color}]")

    console.print(table)

    console.print(
        f"\n  Recommendation: {_recommendation_badge(rv.recommendation)}"
    )
    console.print(f"\n  [dim]{rv.summary}[/dim]")


# ---------------------------------------------------------------------------
# Pipeline runner with step-by-step output
# ---------------------------------------------------------------------------

def run_scenario(pipeline, inp: PipelineInput) -> None:
    label = SCENARIO_LABELS[inp.patient_id]
    console.print(Panel(f"[bold]{label}[/bold]\nPatient ID: [cyan]{inp.patient_id}[/cyan]  |  Edit positions: {inp.edit_positions}", expand=False))

    initial_state: PipelineState = {
        "input": inp,
        "structural": None,
        "hla_binding": None,
        "tcr_result": None,
        "bcell_result": None,
        "reactivity": None,
        "systems": None,
        "risk_vector": None,
        "clinical_report": None,
        "retry_count": 0,
    }

    final_state = None
    visited_stages: list[str] = []

    for chunk in pipeline.stream(initial_state, stream_mode="updates"):
        for node_name, updates in chunk.items():
            visited_stages.append(node_name)

            if node_name == "stage1":
                s = updates["structural"]
                status = f"pLDDT={s.plddt_score:.1f}  SASA={s.sasa_edit_zone:.1f}Å²  exposed={s.edit_zone_exposed}  confidence=[bold]{s.confidence}[/bold]"
                if s.fallback_mode:
                    status += "  [yellow](fallback mode)[/yellow]"
                print_stage_header("Stage 1 — Structural (AlphaFold3/ESMFold + SASA)", status)

            elif node_name == "increment_retry":
                print_stage_header("↺ Retry triggered", "low pLDDT detected — re-running in fallback mode")

            elif node_name == "stage2":
                h = updates["hla_binding"]
                binders = len([b for b in h.class_i_binders if b.strength != "none"]) + len([b for b in h.class_ii_binders if b.strength != "none"])
                status = (
                    f"Class I top %Rank={h.top_class_i_rank:.2f}  "
                    f"Class II top %Rank={h.top_class_ii_rank:.2f}  "
                    f"[{'red' if binders else 'green'}]→ {binders} significant binder(s)[/{'red' if binders else 'green'}]"
                )
                print_stage_header("Stage 2 — HLA Presentation (NetChop + NetMHCpan)", status)

            elif node_name == "stage3_tcr":
                t = updates["tcr_result"]
                status = f"Peptide={t.peptide}  prob={t.binding_probability:.2f}  above_threshold={t.above_threshold}"
                print_stage_header("Stage 3a — T-Cell Branch (NetTCR-2.0) [parallel]", status)

            elif node_name == "stage3_bcell":
                b = updates["bcell_result"]
                status = f"BepiPred={b.bcell_score:.2f}  epitope_detected={b.epitope_detected}  residues={b.epitope_residues}"
                print_stage_header("Stage 3b — B-Cell Branch (BepiPred) [parallel]", status)

            elif node_name == "stage3_join":
                r = updates["reactivity"]
                flag = "[red]HIGH RISK FLAG SET[/red]" if r.high_risk_flag else "[green]within tolerance[/green]"
                print_stage_header("Stage 3 — Reactivity Join", flag)

            elif node_name == "stage4":
                sys = updates["systems"]
                toxic = [p.tissue for p in sys.perturbations if p.toxicity_flag]
                splice_note = f"  cryptic_splice=[yellow]YES[/yellow]  delta_psi={sys.splice.delta_psi:.2f}" if sys.splice.cryptic_sites_detected else ""
                status = f"stability={sys.overall_stability_score:.2f}  toxic_tissues={toxic or 'none'}{splice_note}"
                print_stage_header("Stage 4 — Systems Dynamics (GenBio AI AIDO)", status)

            elif node_name == "aggregate":
                # Merge aggregate updates; report node will follow
                final_state = {**initial_state, **updates}

            elif node_name == "report":
                final_state = {**(final_state or initial_state), **updates}

    console.print("\n")
    if final_state and final_state.get("risk_vector"):
        print_risk_vector(final_state["risk_vector"])
    if final_state and final_state.get("clinical_report"):
        print_clinical_report(final_state["clinical_report"])
    console.print("\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    console.print(
        Panel.fit(
            "[bold white]Multiscale In Silico Immunogenicity Pipeline[/bold white]\n"
            "[dim]Agentic safety screening for gene editing therapies[/dim]",
            border_style="cyan",
        )
    )

    pipeline = build_graph()

    for scenario_input in SCENARIOS:
        run_scenario(pipeline, scenario_input)
        console.rule(style="dim")
