"""
In-process session store for the orchestrator.

Each pipeline run is keyed by a UUID session_id. The orchestrator writes to
sessions as stage responses arrive; the Stage3 sync flags coordinate the
parallel T-cell / B-cell branches.

Thread safety: uagents runs a single asyncio event loop. All on_message
handlers are coroutines on that loop; there is no true concurrency within
a handler, so no locking is needed.
"""

import time
from dataclasses import dataclass, field
from typing import Optional

from src.models.pipeline import (
    PipelineInput,
    StructuralResult,
    HLABindingResult,
    TCRResult,
    BCellResult,
    ReactivityResult,
    SystemsResult,
)


@dataclass
class PipelineSession:
    session_id: str
    client_address: str
    pipeline_input: PipelineInput

    # Stage results — filled in as responses arrive
    structural: Optional[StructuralResult] = None
    hla_binding: Optional[HLABindingResult] = None
    tcr_result: Optional[TCRResult] = None
    bcell_result: Optional[BCellResult] = None
    reactivity: Optional[ReactivityResult] = None
    systems: Optional[SystemsResult] = None

    # Stage 3 parallel sync
    tcr_done: bool = False
    bcell_done: bool = False

    # Stage 1 retry bookkeeping
    retry_count: int = 0

    # For timeout cleanup
    created_at: float = field(default_factory=time.monotonic)

    @property
    def patient_id(self) -> str:
        return self.pipeline_input.patient_id
