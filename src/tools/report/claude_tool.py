"""
Claude-powered clinical report generator.

Uses claude-opus-4-6 with adaptive thinking and structured output via
client.messages.parse() to return a validated ClinicalReport directly.

Activated automatically when ANTHROPIC_API_KEY is set.
Swap to ASI:One by setting REPORT_LLM=asi1 (see asi1_tool.py).
"""

from __future__ import annotations
from typing import TYPE_CHECKING

import anthropic

from src.models.pipeline import ClinicalReport
from src.tools.base import ReportTool
from src.tools.report.context import build_pipeline_context

if TYPE_CHECKING:
    from src.models.pipeline import PipelineState

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
- Note that this is an in silico prediction and does not replace wet-lab validation"""


class ClaudeReportTool(ReportTool):
    def __init__(self, model: str = "claude-opus-4-6") -> None:
        self._client = anthropic.Anthropic()
        self._model = model

    def generate(self, state: "PipelineState") -> ClinicalReport:
        context = build_pipeline_context(state)

        user_prompt = (
            "Please generate a structured clinical safety report for the following "
            "gene therapy edit screening results.\n\n"
            f"{context}\n\n"
            "Produce a report with:\n"
            "1. headline — one concise sentence summarising the safety verdict\n"
            "2. stage_findings — one plain-language finding per pipeline stage\n"
            "3. risk_rationale — 2-3 sentences explaining the overall risk score and "
            "the dominant biological mechanism driving it\n"
            "4. mitigation_suggestions — concrete, actionable next steps "
            "(empty list if recommendation is 'safe')\n"
            "5. confidence_note — brief caveats about prediction confidence, tool "
            "limitations, or the in silico vs. in vivo gap"
        )

        response = self._client.messages.parse(
            model=self._model,
            max_tokens=2048,
            thinking={"type": "adaptive"},
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
            output_format=ClinicalReport,
        )

        return response.parsed_output
