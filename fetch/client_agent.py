"""
Test client agent for the immunogenicity pipeline.

Sends one PipelineRequest per demo scenario on startup and logs the response.
Used with bureau.py for local end-to-end testing without Agentverse.

Usage (via bureau):
    uv run python -m fetch.bureau

Usage (standalone, against a running pipeline agent):
    PIPELINE_AGENT_ADDRESS=agent1q... uv run python -m fetch.client_agent
"""

import asyncio
import os

try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from uagents import Agent, Context

from fetch.messages import PipelineRequest, PipelineResponse

# When running via bureau.py, the address is injected at construction time.
# When running standalone, read it from the environment.
_FALLBACK_ADDRESS = os.getenv("PIPELINE_AGENT_ADDRESS", "")

# Representative test cases — one per pipeline outcome
_TEST_REQUESTS = [
    PipelineRequest(
        patient_id="HIGH_RISK",
        sequence=(
            "MVLSPADKTNVKAAWGKVGAHAGEYGAEALERMFLSFPTTKTYFPHFDLSHGSAQVKGHGKKVADALTNAVAHVDDMPNAL"
            "SALSDLHAHKLRVDPVNFKLLSHCLLVTLAAHLPAEFTPAVHASLDKFLASVSTVLTSKYR"
        ),
        edit_positions=[47, 48, 49, 50, 51, 52, 53],
        hla_profile=["HLA-A*02:01", "HLA-B*07:02", "HLA-C*07:02", "HLA-DRB1*01:01"],
    ),
    PipelineRequest(
        patient_id="LOW_IMMUNOGENIC",
        sequence=(
            "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSY RKQVVIDGETCLLDILDTAGQEEYSAMRDQYMRT"
            "GEGFLCVFAINNTKSFEDIHHQRQEIKRVKDSEDVPMVLVGNKCDLPARTVETRQAQDLARSYGIPYIETSAKTR"
        ),
        edit_positions=[12, 13],
        hla_profile=["HLA-A*01:01", "HLA-B*08:01", "HLA-DRB1*03:01"],
    ),
    PipelineRequest(
        patient_id="SYSTEMS_FAILURE",
        sequence=(
            "MALSLEAPQMAVVSREALVALVQERQKKLAKQEEEDLKKLEKEAEKELRQRQERLKQEREKMLMEQLEKRLQAL"
            "EEAQRREAEHLRRQLTDLQEELMKKLNREAFKQLEEERQLKVELEEMQRREDELRQKLEEELRKAQEELRRTLEDKKE"
        ),
        edit_positions=[22, 23, 24, 25],
        hla_profile=["HLA-A*02:01", "HLA-B*35:01", "HLA-DRB1*04:01"],
    ),
    PipelineRequest(
        patient_id="ALL_CLEAR",
        sequence=(
            "MSHHWGYGKHNGPEHWHKDFPIAKGERQSPVDIDTHTAKYDPSLKPLSVSYDQATSLRILNNGAAFNVEFDDSQDKAVL"
            "KGGPLDGTYRLIQFHFHWGSLDGQGSEHTVDKKKYAAELHLVHWNTKYGDFGTAAQQPDGLAVLGIFLKVGSAKPGLQKVVDVLDSIK"
        ),
        edit_positions=[8, 9],
        hla_profile=["HLA-A*03:01", "HLA-B*07:02", "HLA-DRB1*15:01"],
    ),
]

_RECOMMENDATION_LABEL = {
    "safe":      "SAFE",
    "caution":   "CAUTION",
    "high_risk": "HIGH RISK",
    "error":     "ERROR",
}


def create_client_agent(pipeline_address: str = _FALLBACK_ADDRESS) -> Agent:
    """
    Factory so bureau.py can inject the pipeline agent address at runtime
    rather than relying on an environment variable.
    """
    client = Agent(
        name="pipeline-client",
        seed="immunogenicity_pipeline_client_seed_2026",
        port=8001,
        endpoint=["http://127.0.0.1:8001/submit"],
    )

    @client.on_event("startup")
    async def send_requests(ctx: Context) -> None:
        if not pipeline_address:
            ctx.logger.error(
                "No pipeline agent address. Set PIPELINE_AGENT_ADDRESS or use bureau.py."
            )
            return

        ctx.logger.info(f"Sending {len(_TEST_REQUESTS)} test requests to {pipeline_address[:24]}...")
        for req in _TEST_REQUESTS:
            await ctx.send(pipeline_address, req)

    @client.on_message(model=PipelineResponse)
    async def handle_response(ctx: Context, sender: str, msg: PipelineResponse) -> None:
        if msg.error:
            ctx.logger.error(f"[{msg.patient_id}] Pipeline error: {msg.error}")
            return

        label = _RECOMMENDATION_LABEL.get(msg.recommendation, msg.recommendation.upper())
        ctx.logger.info(
            f"[{msg.patient_id}] {label} | "
            f"overall={msg.overall_risk:.3f} "
            f"struct={msg.structural_risk:.3f} "
            f"immuno={msg.immunogenic_risk:.3f} "
            f"react={msg.reactivity_risk:.3f} "
            f"sys={msg.systems_risk:.3f}"
        )
        ctx.logger.info(f"[{msg.patient_id}] {msg.summary}")

    return client


if __name__ == "__main__":
    # Standalone mode: pipeline agent must already be running
    agent = create_client_agent()
    agent.run()
