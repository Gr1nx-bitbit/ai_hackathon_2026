"""
Abstract interfaces for each pipeline tool.

To swap a mock for a real binary, subclass the relevant ABC and register it
in registry.py. The graph nodes never import concrete implementations directly.
"""

from abc import ABC, abstractmethod

from src.models.pipeline import (
    PipelineInput,
    StructuralResult,
    HLABindingResult,
    TCRResult,
    BCellResult,
    SystemsResult,
    ClinicalReport,
    PipelineState,
)


class StructuralTool(ABC):
    """
    Predicts 3D conformation and surface exposure of the edited protein.
    Real implementation: AlphaFold3 or ESMFold + SASA calculation (BioPython/FreeSASA).
    """

    @abstractmethod
    def predict(self, inp: PipelineInput, fallback_mode: bool = False) -> StructuralResult:
        """
        Args:
            inp: Full pipeline input including sequence and edit positions.
            fallback_mode: When True (retry pass), skip structure prediction and
                           return a conservative sequence-only result with high
                           surface-exposure assumption.
        """
        ...


class HLABindingTool(ABC):
    """
    Predicts proteasomal cleavage windows and HLA Class I/II binding affinity.
    Real implementation: NetChop-3.1 + NetMHCpan-4.1 / NetMHCIIpan-4.0.
    """

    @abstractmethod
    def predict(self, inp: PipelineInput, structural: StructuralResult) -> HLABindingResult:
        """
        Args:
            inp: Pipeline input; hla_profile drives the allele set for pan-HLA scoring.
            structural: Used to weight cleavage windows by surface accessibility.
        """
        ...


class TCRTool(ABC):
    """
    Evaluates high-affinity HLA binders for T-cell receptor recognition probability.
    Real implementation: NetTCR-2.0.
    """

    @abstractmethod
    def predict(self, inp: PipelineInput, hla_binding: HLABindingResult) -> TCRResult:
        """
        Evaluates the top-ranked Class I binder from HLA stage output.
        """
        ...


class BCellTool(ABC):
    """
    Predicts linear B-cell epitopes in the edit zone sequence window.
    Real implementation: BepiPred via IEDB REST API.
    Note: BepiPred predicts linear (sequential) epitopes; conformational
    epitope prediction (e.g., DiscoTope-3.0) would require a PDB structure as
    input. For a POC pipeline, linear prediction captures the dominant pathway.
    """

    @abstractmethod
    def predict(self, inp: PipelineInput, structural: StructuralResult) -> BCellResult:
        """
        Evaluates the edit zone for B-cell epitope likelihood using
        BepiPred propensity scores.
        """
        ...


class SystemsTool(ABC):
    """
    Simulates functional aftermath of the edit inside the cell ecosystem.
    Real implementation: GenBio AI AIDO (ModelGenerator) — AIDO.RNA, AIDO.DNA, AIDO.Cell.
    """

    @abstractmethod
    def predict(self, inp: PipelineInput) -> SystemsResult:
        """
        Runs:
          - AIDO.RNA/DNA: splice site and isoform stability check
          - AIDO.Cell: whole-transcriptome single-cell perturbation across target tissues
        """
        ...


class ReportTool(ABC):
    """
    Generates a plain-language clinical safety report from the full pipeline state.
    Real implementation: Claude (claude-opus-4-6) or ASI:One.
    Mock implementation: returns canned scenario-specific text.
    """

    @abstractmethod
    def generate(self, state: "PipelineState") -> ClinicalReport:
        """
        Receives the complete pipeline state (all stage outputs + risk vector)
        and returns a structured clinical report intended for physician review.
        """
        ...
