"""
ASI:One clinical report generator.

ASI:One (Artificial Superintelligence Alliance — the merged AI from Fetch.ai,
SingularityNET, and Ocean Protocol) exposes an OpenAI-compatible chat API.

Activate by setting:
    export REPORT_LLM=asi1
    export ASI1_API_KEY=<your key>

Or let the registry auto-select it when ASI1_API_KEY is present:
    export ASI1_API_KEY=<your key>          # REPORT_LLM defaults to "auto"

The clinical report prompt and context are shared with the Claude implementation
(src/tools/report/context.py). Only the API call differs.

Configuration:
    ASI1_API_KEY      Required. Your ASI:One API key.
    ASI1_MODEL        Model to use. Defaults to "asi1-mini".
                      Check https://api.asi1.ai/v1/models for available models.
    ASI1_API_BASE_URL Defaults to "https://api.asi1.ai/v1". Override if needed.
    ASI1_MAX_TOKENS   Defaults to 2048.
"""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING

from src.models.pipeline import ClinicalReport
from src.tools.base import ReportTool
from src.tools.report.context import build_pipeline_context

if TYPE_CHECKING:
    from src.models.pipeline import PipelineState

logger = logging.getLogger(__name__)

_API_KEY  = os.getenv("ASI1_API_KEY", "")
_BASE_URL = os.getenv("ASI1_API_BASE_URL", "https://api.asi1.ai/v1")
_MODEL    = os.getenv("ASI1_MODEL", "asi1-mini")
_MAX_TOKENS = int(os.getenv("ASI1_MAX_TOKENS", "2048"))

_SYSTEM_PROMPT = """You are a clinical gene therapy safety analyst reviewing in silico \
immunogenicity and systems safety screening results.

Your audience:
- Treating physician — needs a clear, plain-language verdict and actionable guidance
- Gene therapy team — needs scientific specifics and biological mechanism rationale
- Regulatory reviewers — needs structured, comprehensive documentation

Guidelines:
- Be precise and scientifically accurate; use standard gene therapy safety terminology
- Distinguish clearly between what the data shows vs. what it implies clinically
- For SAFE results: acknowledge what passed and note appropriate monitoring
- For CAUTION results: identify the dominant concern and its biological mechanism
- For HIGH RISK results: focus on the specific pathway driving the risk and name \
concrete alternatives (sequence modifications, delivery route changes, vector choice, etc.)
- Note that this is an in silico prediction and does not replace wet-lab validation

You must respond with valid JSON matching this exact schema:
{
  "headline": "<one concise sentence summarising the safety verdict>",
  "stage_findings": ["<finding for stage 1>", "<finding for stage 2>", ...],
  "risk_rationale": "<2-3 sentences on overall risk score and dominant biological mechanism>",
  "mitigation_suggestions": ["<actionable step 1>", ...],
  "confidence_note": "<caveats about prediction confidence and in silico vs. in vivo gap>"
}
Return only the JSON object — no markdown fences, no preamble."""


class ASI1ReportTool(ReportTool):
    """
    Clinical report generator powered by ASI:One.

    Uses the OpenAI-compatible ASI:One API with response_format=json_object
    to return a structured ClinicalReport validated against the Pydantic schema.
    """

    def __init__(self) -> None:
        # Read at instantiation time so runtime env changes are picked up
        api_key = os.getenv("ASI1_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "ASI1_API_KEY is not set. "
                "Set it in your environment to use the ASI:One report tool."
            )
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError(
                "The 'openai' package is required for ASI1ReportTool. "
                "Install it with: uv add openai"
            ) from exc

        self._client = OpenAI(api_key=api_key, base_url=_BASE_URL)
        logger.info(f"ASI1ReportTool: using model={_MODEL} base_url={_BASE_URL}")

    def generate(self, state: "PipelineState") -> ClinicalReport:
        context = build_pipeline_context(state)

        user_prompt = (
            "Please generate a structured clinical safety report for the following "
            "gene therapy edit screening results.\n\n"
            f"{context}\n\n"
            "Produce a JSON report with:\n"
            "1. headline — one concise sentence summarising the safety verdict\n"
            "2. stage_findings — one plain-language finding per pipeline stage\n"
            "3. risk_rationale — 2-3 sentences on the overall risk score and the "
            "dominant biological mechanism driving it\n"
            "4. mitigation_suggestions — concrete, actionable next steps "
            "(empty list if recommendation is 'safe')\n"
            "5. confidence_note — brief caveats about prediction confidence, tool "
            "limitations, or the in silico vs. in vivo gap"
        )

        logger.info(
            f"[{state['input'].patient_id}] ASI:One report: "
            f"model={_MODEL} context_len={len(context)} chars"
        )

        response = self._client.chat.completions.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
        )

        raw = response.choices[0].message.content or "{}"
        logger.debug(f"[{state['input'].patient_id}] ASI:One raw response: {raw[:200]}...")

        try:
            return ClinicalReport.model_validate_json(raw)
        except Exception as exc:
            # If the model returned valid JSON but with slightly wrong keys,
            # try to extract what we can before giving up.
            logger.warning(
                f"[{state['input'].patient_id}] ASI:One response failed schema validation "
                f"({exc}) — attempting partial extraction"
            )
            data = json.loads(raw)
            return ClinicalReport(
                headline=data.get("headline", "Clinical report generation encountered an error."),
                stage_findings=data.get("stage_findings", []),
                risk_rationale=data.get("risk_rationale", ""),
                mitigation_suggestions=data.get("mitigation_suggestions", []),
                confidence_note=data.get(
                    "confidence_note",
                    "Report generation encountered an error. Review raw pipeline scores directly."
                ),
            )
