"""
Tool registry — the single place where mock ↔ real implementations are swapped.

Usage:
    from src.tools.registry import get_structural_tool
    tool = get_structural_tool()          # returns mock by default
    tool = get_structural_tool("real")    # returns real implementation once available

To wire in a real binary, implement the corresponding ABC from tools/base.py,
then add it to the _REAL_* dicts below and flip the default mode.
"""

import os
from typing import Literal

from src.tools.base import StructuralTool, HLABindingTool, TCRTool, BCellTool, SystemsTool, ReportTool
from src.tools.mock import (
    MockStructuralTool,
    MockHLABindingTool,
    MockTCRTool,
    MockBCellTool,
    MockSystemsTool,
)
from src.tools.report import MockReportTool

Mode = Literal["mock", "real"]

# Set PIPELINE_MODE=real in environment to switch globally once real tools are available
_DEFAULT_MODE: Mode = os.getenv("PIPELINE_MODE", "mock")  # type: ignore[assignment]


def get_structural_tool(mode: Mode = _DEFAULT_MODE) -> StructuralTool:
    if mode == "real" or os.getenv("ESMFOLD_ENABLED", "").lower() in ("1", "true"):
        from src.tools.real.structural_tool import ESMFoldStructuralTool
        return ESMFoldStructuralTool()
    return MockStructuralTool()


def get_hla_tool(mode: Mode = _DEFAULT_MODE) -> HLABindingTool:
    # IEDB can be enabled independently without switching the whole pipeline to "real"
    if mode == "real" or os.getenv("IEDB_ENABLED", "").lower() in ("1", "true"):
        from src.tools.real.hla_tool import IEDBHLABindingTool
        return IEDBHLABindingTool()
    return MockHLABindingTool()


def get_tcr_tool(mode: Mode = _DEFAULT_MODE) -> TCRTool:
    if mode == "real":
        raise NotImplementedError("Real TCRTool (NetTCR-2.0 Docker service) not yet wired.")
    return MockTCRTool()


def get_bcell_tool(mode: Mode = _DEFAULT_MODE) -> BCellTool:
    if mode == "real" or os.getenv("BEPIPRED_ENABLED", "").lower() in ("1", "true"):
        from src.tools.real.bcell_tool import BepiPredBCellTool
        return BepiPredBCellTool()
    return MockBCellTool()


def get_systems_tool(mode: Mode = _DEFAULT_MODE) -> SystemsTool:
    if mode == "real":
        raise NotImplementedError("Real SystemsTool (GenBio AI AIDO API) not yet wired.")
    return MockSystemsTool()


def get_report_tool() -> ReportTool:
    """
    Auto-selects the report tool based on environment:

      REPORT_LLM=asi1    + ASI1_API_KEY set        → ASI1ReportTool
      REPORT_LLM=claude  + ANTHROPIC_API_KEY set   → ClaudeReportTool (claude-opus-4-6)
      REPORT_LLM=mock                              → MockReportTool (forced)
      REPORT_LLM=auto (default):
        1. ASI1_API_KEY set   → ASI1ReportTool
        2. ANTHROPIC_API_KEY  → ClaudeReportTool
        3. neither            → MockReportTool
    """
    llm = os.getenv("REPORT_LLM", "auto").lower()

    if llm == "mock":
        return MockReportTool()

    if llm == "asi1":
        from src.tools.report.asi1_tool import ASI1ReportTool
        return ASI1ReportTool()

    if llm == "claude":
        from src.tools.report.claude_tool import ClaudeReportTool
        return ClaudeReportTool()

    # "auto": prefer ASI:One → Claude → mock
    if os.getenv("ASI1_API_KEY"):
        from src.tools.report.asi1_tool import ASI1ReportTool
        return ASI1ReportTool()

    if os.getenv("ANTHROPIC_API_KEY"):
        from src.tools.report.claude_tool import ClaudeReportTool
        return ClaudeReportTool()

    return MockReportTool()
