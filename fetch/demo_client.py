"""
Demo client — send a request to the orchestrator (full pipeline) or any
individual specialist agent directly.

Usage:
    # Full pipeline via orchestrator
    uv run python -m fetch.demo_client --target orchestrator
    uv run python -m fetch.demo_client --target orchestrator --scenario early_exit

    # Individual stages (showcases direct Agentverse composability)
    uv run python -m fetch.demo_client --target stage1
    uv run python -m fetch.demo_client --target stage2
    uv run python -m fetch.demo_client --target stage3-tcr
    uv run python -m fetch.demo_client --target stage3-bcell
    uv run python -m fetch.demo_client --target stage4

Required env vars (printed by bureau_multi on startup):
    ORCHESTRATOR_AGENT_ADDRESS
    STAGE1_AGENT_ADDRESS
    STAGE2_AGENT_ADDRESS
    STAGE3_TCR_AGENT_ADDRESS
    STAGE3_BCELL_AGENT_ADDRESS
    STAGE4_AGENT_ADDRESS

Set AGENTVERSE_MAILBOX=1 to route through Agentverse instead of local delivery.
"""

import argparse
import asyncio
import json
import os
import uuid

try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from uagents import Agent, Context

from fetch.messages import PipelineRequest, PipelineResponse
from fetch.multi.messages import (
    AgentError,
    Stage1Request, Stage1Response,
    Stage2Request, Stage2Response,
    Stage3BcellRequest, Stage3BcellResponse,
    Stage3TcrRequest, Stage3TcrResponse,
    Stage4Request, Stage4Response,
)
from src.models.pipeline import PipelineInput

console = Console()

# ---------------------------------------------------------------------------
# Scenario definitions (shared with client_agent.py)
# ---------------------------------------------------------------------------

_SCENARIOS: dict[str, PipelineInput] = {
    "high_risk": PipelineInput(
        patient_id="HIGH_RISK",
        sequence=(
            "MVLSPADKTNVKAAWGKVGAHAGEYGAEALERMFLSFPTTKTYFPHFDLSHGSAQVKGHGKKVADALTNAVAHVDDMPNAL"
            "SALSDLHAHKLRVDPVNFKLLSHCLLVTLAAHLPAEFTPAVHASLDKFLASVSTVLTSKYR"
        ),
        edit_positions=[47, 48, 49, 50, 51, 52, 53],
        hla_profile=["HLA-A*02:01", "HLA-B*07:02", "HLA-C*07:02", "HLA-DRB1*01:01"],
    ),
    "early_exit": PipelineInput(
        patient_id="EARLY_EXIT",
        sequence=(
            "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSY RKQVVIDGETCLLDILDTAGQEEYSAMRDQYMRT"
            "GEGFLCVFAINNTKSFEDIHHQRQEIKRVKDSEDVPMVLVGNKCDLPARTVETRQAQDLARSYGIPYIETSAKTR"
        ),
        edit_positions=[12, 13],
        hla_profile=["HLA-A*01:01", "HLA-B*08:01", "HLA-DRB1*03:01"],
    ),
    "systems_failure": PipelineInput(
        patient_id="SYSTEMS_FAILURE",
        sequence=(
            "MALSLEAPQMAVVSREALVALVQERQKKLAKQEEEDLKKLEKEAEKELRQRQERLKQEREKMLMEQLEKRLQAL"
            "EEAQRREAEHLRRQLTDLQEELMKKLNREAFKQLEEERQLKVELEEMQRREDELRQKLEEELRKAQEELRRTLEDKKE"
        ),
        edit_positions=[22, 23, 24, 25],
        hla_profile=["HLA-A*02:01", "HLA-B*35:01", "HLA-DRB1*04:01"],
    ),
    "all_clear": PipelineInput(
        patient_id="ALL_CLEAR",
        sequence=(
            "MSHHWGYGKHNGPEHWHKDFPIAKGERQSPVDIDTHTAKYDPSLKPLSVSYDQATSLRILNNGAAFNVEFDDSQDKAVL"
            "KGGPLDGTYRLIQFHFHWGSLDGQGSEHTVDKKKYAAELHLVHWNTKYGDFGTAAQQPDGLAVLGIFLKVGSAKPGLQKVVDVLDSIK"
        ),
        edit_positions=[8, 9],
        hla_profile=["HLA-A*03:01", "HLA-B*07:02", "HLA-DRB1*15:01"],
    ),
}

# ---------------------------------------------------------------------------
# Address map
# ---------------------------------------------------------------------------

_ADDRESSES = {
    "orchestrator": os.getenv("ORCHESTRATOR_AGENT_ADDRESS", ""),
    "stage1":       os.getenv("STAGE1_AGENT_ADDRESS", ""),
    "stage2":       os.getenv("STAGE2_AGENT_ADDRESS", ""),
    "stage3-tcr":   os.getenv("STAGE3_TCR_AGENT_ADDRESS", ""),
    "stage3-bcell": os.getenv("STAGE3_BCELL_AGENT_ADDRESS", ""),
    "stage4":       os.getenv("STAGE4_AGENT_ADDRESS", ""),
}

# ---------------------------------------------------------------------------
# Request builders — stages 2+ need mock upstream data as inputs
# ---------------------------------------------------------------------------

def _build_request(target: str, inp: PipelineInput, session_id: str):
    """Build the appropriate request message for the given target stage."""
    from src.tools.registry import get_structural_tool, get_hla_tool

    if target == "orchestrator":
        return PipelineRequest(
            patient_id=inp.patient_id,
            sequence=inp.sequence,
            edit_positions=inp.edit_positions,
            hla_profile=inp.hla_profile,
        )

    if target == "stage1":
        return Stage1Request(
            session_id=session_id,
            patient_id=inp.patient_id,
            sequence=inp.sequence,
            edit_positions=inp.edit_positions,
            hla_profile=inp.hla_profile,
        )

    # Stages 2+ need upstream mock outputs as inputs
    structural = get_structural_tool().predict(inp)

    if target == "stage2":
        return Stage2Request(
            session_id=session_id,
            input_json=inp.model_dump_json(),
            structural_json=structural.model_dump_json(),
        )

    hla = get_hla_tool().predict(inp, structural)

    if target == "stage3-tcr":
        return Stage3TcrRequest(
            session_id=session_id,
            input_json=inp.model_dump_json(),
            hla_binding_json=hla.model_dump_json(),
        )

    if target == "stage3-bcell":
        return Stage3BcellRequest(
            session_id=session_id,
            input_json=inp.model_dump_json(),
            structural_json=structural.model_dump_json(),
        )

    if target == "stage4":
        return Stage4Request(
            session_id=session_id,
            input_json=inp.model_dump_json(),
        )

    raise ValueError(f"Unknown target: {target}")

# ---------------------------------------------------------------------------
# Response display helpers
# ---------------------------------------------------------------------------

def _show_pipeline_response(msg: PipelineResponse) -> None:
    colour = {"safe": "green", "caution": "yellow", "high_risk": "red", "error": "red"}.get(
        msg.recommendation, "white"
    )
    exit_note = f"  Early exit at stage {msg.early_exit_stage}" if msg.early_exit_stage else ""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_row("Recommendation", f"[bold {colour}]{msg.recommendation.upper()}[/]")
    table.add_row("Overall risk",   f"{msg.overall_risk:.3f}{exit_note}")
    table.add_row("Structural",     f"{msg.structural_risk:.3f}")
    table.add_row("Immunogenic",    f"{msg.immunogenic_risk:.3f}")
    table.add_row("Reactivity",     f"{msg.reactivity_risk:.3f}")
    table.add_row("Systems",        f"{msg.systems_risk:.3f}")
    console.print(Panel(table, title=f"[bold]Pipeline result — {msg.patient_id}[/]", border_style=colour))
    if msg.summary:
        console.print(f"[dim]{msg.summary}[/dim]\n")


def _show_stage1(msg: Stage1Response) -> None:
    from src.models.pipeline import StructuralResult
    r = StructuralResult.model_validate_json(msg.structural_json)
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_row("pLDDT score",    f"{r.plddt_score:.1f}")
    table.add_row("Confidence",     f"[bold]{r.confidence}[/]")
    table.add_row("SASA (edit zone)", f"{r.sasa_edit_zone:.1f} Å²")
    table.add_row("Surface exposed", "[red]YES[/]" if r.edit_zone_exposed else "[green]NO[/]")
    table.add_row("Fallback mode",  str(r.fallback_mode))
    console.print(Panel(table, title="[bold]Stage 1 — Structural result[/]", border_style="blue"))


def _show_stage2(msg: Stage2Response) -> None:
    from src.models.pipeline import HLABindingResult
    r = HLABindingResult.model_validate_json(msg.hla_binding_json)
    colour = "green" if r.early_exit else "red"
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_row("Early exit", f"[bold {colour}]{r.early_exit}[/]")
    table.add_row("Top Class I %Rank",  f"{r.top_class_i_rank:.2f}")
    table.add_row("Top Class II %Rank", f"{r.top_class_ii_rank:.2f}")
    if r.class_i_binders:
        b = r.class_i_binders[0]
        table.add_row("Best Class I binder", f"{b.peptide}  {b.hla_allele}  IC50={b.ic50_nm:.0f} nM  [{b.strength}]")
    console.print(Panel(table, title="[bold]Stage 2 — HLA binding result[/]", border_style="blue"))


def _show_stage3_tcr(msg: Stage3TcrResponse) -> None:
    from src.models.pipeline import TCRResult
    r = TCRResult.model_validate_json(msg.tcr_json)
    colour = "red" if r.above_threshold else "green"
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_row("Peptide",            r.peptide)
    table.add_row("HLA allele",         r.hla_allele)
    table.add_row("Binding probability", f"{r.binding_probability:.3f}")
    table.add_row("Above threshold",    f"[bold {colour}]{r.above_threshold}[/]")
    console.print(Panel(table, title="[bold]Stage 3a — T-cell reactivity result[/]", border_style="blue"))


def _show_stage3_bcell(msg: Stage3BcellResponse) -> None:
    from src.models.pipeline import BCellResult
    r = BCellResult.model_validate_json(msg.bcell_json)
    colour = "red" if r.epitope_detected else "green"
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_row("B-cell score",    f"{r.bcell_score:.3f}")
    table.add_row("Epitope detected", f"[bold {colour}]{r.epitope_detected}[/]")
    if r.epitope_residues:
        table.add_row("Epitope residues", ", ".join(str(i) for i in r.epitope_residues))
    console.print(Panel(table, title="[bold]Stage 3b — B-cell reactivity result[/]", border_style="blue"))


def _show_stage4(msg: Stage4Response) -> None:
    from src.models.pipeline import SystemsResult
    r = SystemsResult.model_validate_json(msg.systems_json)
    colour = "red" if r.overall_stability_score < 0.5 else "yellow" if r.overall_stability_score < 0.75 else "green"
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_row("Stability score",   f"[bold {colour}]{r.overall_stability_score:.3f}[/]")
    table.add_row("Cryptic splice sites", str(r.splice.cryptic_sites_detected))
    table.add_row("Splice delta PSI",  f"{r.splice.delta_psi:.3f}")
    for pert in r.perturbations:
        table.add_row(f"Toxicity ({pert.tissue})", str(pert.toxicity_flag))
    console.print(Panel(table, title="[bold]Stage 4 — Systems dynamics result[/]", border_style="blue"))

# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Immunogenicity pipeline demo client")
    parser.add_argument(
        "--target",
        choices=["orchestrator", "stage1", "stage2", "stage3-tcr", "stage3-bcell", "stage4"],
        default="orchestrator",
        help="Which agent to call (default: orchestrator)",
    )
    parser.add_argument(
        "--scenario",
        choices=list(_SCENARIOS),
        default="high_risk",
        help="Demo scenario to use (default: high_risk)",
    )
    return parser.parse_args()


def create_demo_client(target: str, scenario: str) -> Agent:
    address = _ADDRESSES[target]
    if not address:
        env_var = target.upper().replace("-", "_") + "_AGENT_ADDRESS"
        if target == "orchestrator":
            env_var = "ORCHESTRATOR_AGENT_ADDRESS"
        raise SystemExit(
            f"ERROR: {env_var} is not set.\n"
            "Copy the address from the bureau_multi startup log and export it."
        )

    inp = _SCENARIOS[scenario]
    session_id = str(uuid.uuid4())
    use_mailbox = bool(os.getenv("AGENTVERSE_MAILBOX"))

    client = Agent(
        name="demo-client",
        seed="imm_demo_client_seed_2026",
        port=8099,
        endpoint=["http://127.0.0.1:8099/submit"],
        mailbox=use_mailbox,
    )

    @client.on_event("startup")
    async def send_request(ctx: Context) -> None:
        console.print(f"\n[bold]Target:[/]   [cyan]{target}[/]  →  {address[:32]}...")
        console.print(f"[bold]Scenario:[/] [cyan]{scenario}[/]  (patient_id={inp.patient_id})")
        console.print(f"[bold]Mailbox:[/]  {'Agentverse relay' if use_mailbox else 'local'}\n")

        req = await asyncio.to_thread(_build_request, target, inp, session_id)
        await ctx.send(address, req)
        ctx.logger.info("Request sent — waiting for response...")

    @client.on_message(model=PipelineResponse)
    async def on_pipeline(ctx: Context, sender: str, msg: PipelineResponse) -> None:
        _show_pipeline_response(msg)

    @client.on_message(model=Stage1Response)
    async def on_stage1(ctx: Context, sender: str, msg: Stage1Response) -> None:
        _show_stage1(msg)

    @client.on_message(model=Stage2Response)
    async def on_stage2(ctx: Context, sender: str, msg: Stage2Response) -> None:
        _show_stage2(msg)

    @client.on_message(model=Stage3TcrResponse)
    async def on_stage3_tcr(ctx: Context, sender: str, msg: Stage3TcrResponse) -> None:
        _show_stage3_tcr(msg)

    @client.on_message(model=Stage3BcellResponse)
    async def on_stage3_bcell(ctx: Context, sender: str, msg: Stage3BcellResponse) -> None:
        _show_stage3_bcell(msg)

    @client.on_message(model=Stage4Response)
    async def on_stage4(ctx: Context, sender: str, msg: Stage4Response) -> None:
        _show_stage4(msg)

    @client.on_message(model=AgentError)
    async def on_error(ctx: Context, sender: str, msg: AgentError) -> None:
        console.print(f"[bold red]Agent error in {msg.stage}:[/] {msg.error}")

    return client


if __name__ == "__main__":
    args = _parse_args()
    client = create_demo_client(args.target, args.scenario)
    client.run()
