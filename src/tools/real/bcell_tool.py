"""
Real Stage 3b — B-cell epitope prediction via the IEDB Analysis Resource REST API.

Uses BepiPred, a random-forest model trained on crystal-structure-derived
B-cell epitope data. It predicts linear (sequential) epitopes from sequence alone —
no 3D structure required.

Note on linear vs conformational epitopes:
    BepiPred identifies stretches of solvent-exposed residues whose amino acid
    composition matches known B-cell epitopes. ~80-90 % of antibody epitopes are
    conformational (discontinuous in sequence), which this approach cannot detect.
    For a full production pipeline, conformational prediction (e.g., DiscoTope-3.0)
    would be applied to the ESMFold PDB output. For this POC, linear screening is
    a practical, well-validated surrogate that runs without installing additional
    software or model weights.

Activate with:
    export BEPIPRED_ENABLED=1
    uv run python demo.py

Configuration env vars:

    BEPIPRED_ENABLED        Set to "1" to use this tool. Default: "0" (mock).
    IEDB_API_BASE_URL       Override the IEDB endpoint if it changes.
    BEPIPRED_THRESHOLD      Per-residue score threshold for epitope annotation.
                            Default: 0.35 (BepiPred published threshold; score range ≈ −1 to +1).
    BEPIPRED_MIN_LENGTH     Minimum contiguous residues above threshold to call
                            an epitope. Default: 4 (avoids spurious single-residue hits).
    BEPIPRED_CONTEXT        Residues of flanking context to submit around the edit
                            zone. Default: 15 (same as HLA tool).
    BEPIPRED_FULL_SEQUENCE  Set to "1" to submit the full protein. Default: "0".
    IEDB_TIMEOUT            Request timeout in seconds. Default: 60.
    IEDB_VERIFY_SSL         Set to "0" to disable SSL verification. Default: "1".
    IEDB_REQUEST_DELAY      Seconds to sleep before each call. Default: 1.5.
    IEDB_MAX_RETRIES        Retries on 403/429. Default: 3.
    IEDB_RETRY_BACKOFF      Seconds for first retry delay (doubles). Default: 4.0.
"""

from __future__ import annotations

import csv
import io
import logging
import os
import time
from typing import Optional

import requests
import urllib3

from src.tools.base import BCellTool
from src.models.pipeline import PipelineInput, StructuralResult, BCellResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_BASE_URL     = os.getenv("IEDB_API_BASE_URL", "https://tools-cluster-interface.iedb.org/tools_api")
_BCELL_URL    = f"{_BASE_URL}/bcell/"
_TIMEOUT      = int(os.getenv("IEDB_TIMEOUT", "60"))
_VERIFY_SSL   = os.getenv("IEDB_VERIFY_SSL", "1") not in ("0", "false")
_THRESHOLD    = float(os.getenv("BEPIPRED_THRESHOLD", "0.35"))
_MIN_LENGTH   = int(os.getenv("BEPIPRED_MIN_LENGTH", "4"))
_CONTEXT      = int(os.getenv("BEPIPRED_CONTEXT", "15"))
_FULL_SEQ     = os.getenv("BEPIPRED_FULL_SEQUENCE", "0").lower() in ("1", "true")

_REQUEST_DELAY = float(os.getenv("IEDB_REQUEST_DELAY", "1.5"))
_MAX_RETRIES   = int(os.getenv("IEDB_MAX_RETRIES", "3"))
_RETRY_BACKOFF = float(os.getenv("IEDB_RETRY_BACKOFF", "4.0"))

_HEADERS = {"User-Agent": "immunogenicity-pipeline/1.0"}

if not _VERIFY_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    logger.warning(
        "SSL certificate verification disabled (IEDB_VERIFY_SSL=0). "
        "Only use this in a trusted network environment."
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _edit_window(sequence: str, edit_positions: list[int]) -> tuple[str, int]:
    """
    Returns (window_sequence, start_offset_in_full_sequence).

    If BEPIPRED_FULL_SEQUENCE=1 or no edit positions are given, the full
    sequence is returned with offset 0.
    """
    if _FULL_SEQ or not edit_positions:
        return sequence, 0
    lo = max(0, min(edit_positions) - _CONTEXT)
    hi = min(len(sequence), max(edit_positions) + _CONTEXT + 1)
    return sequence[lo:hi], lo


def _post_with_retry(url: str, data: dict) -> str:
    """POST to IEDB with inter-request delay and exponential-backoff retry."""
    time.sleep(_REQUEST_DELAY)
    delay = _RETRY_BACKOFF
    for attempt in range(_MAX_RETRIES + 1):
        resp = requests.post(
            url,
            headers=_HEADERS,
            data=data,
            timeout=_TIMEOUT,
            verify=_VERIFY_SSL,
        )
        if resp.status_code in (403, 429) and attempt < _MAX_RETRIES:
            logger.warning(
                f"IEDB BepiPred returned {resp.status_code} (rate limit?); "
                f"retrying in {delay:.0f}s (attempt {attempt + 1}/{_MAX_RETRIES})"
            )
            time.sleep(delay)
            delay *= 2
            continue
        resp.raise_for_status()
        return resp.text
    resp.raise_for_status()
    return ""


def _parse_scores(tsv_text: str) -> list[tuple[int, float]]:
    """
    Parse the IEDB BepiPred TSV response.

    Returns a list of (1-based position, score) tuples.

    The IEDB BepiPred endpoint returns a TSV with at least these columns:
        position  residue  score  epitope
    where position is 1-based and score is the BepiPred per-residue score
    (0.0 – 1.0). The 'epitope' column uses the default threshold (0.5) so we
    re-apply our own configurable threshold below.
    """
    lines = tsv_text.strip().splitlines()
    if not lines:
        return []

    # Skip comment lines (IEDB sometimes prepends metadata)
    data_lines = [l for l in lines if not l.startswith("#")]
    if not data_lines:
        return []

    reader = csv.DictReader(io.StringIO("\n".join(data_lines)), delimiter="\t")
    results: list[tuple[int, float]] = []
    for row in reader:
        # IEDB BepiPred response columns: Position  Residue  Score  Assignment
        pos_str   = (row.get("Position") or row.get("position") or "").strip()
        score_str = (row.get("Score")    or row.get("score")    or "").strip()
        if not pos_str or not score_str:
            continue
        try:
            results.append((int(pos_str), float(score_str)))
        except ValueError:
            continue
    return results


def _find_epitope_residues(
    scores: list[tuple[int, float]],   # (1-based absolute position, score)
    edit_positions: list[int],          # 0-based original sequence positions
) -> tuple[list[int], float, bool]:
    """
    Identifies predicted epitope residues and computes the mean BepiPred score
    over the edit zone.

    Strategy:
    1. Find all contiguous stretches of residues with score ≥ THRESHOLD and
       length ≥ MIN_LENGTH (the BepiPred "epitope segments").
    2. A segment is relevant if it overlaps any edit position (0-based converted
       to 1-based for comparison with IEDB output).
    3. If any relevant segment exists: epitope_detected = True, epitope_residues
       = positions within that segment that overlap the edit zone.
    4. bcell_score = mean score of edit-zone residues (independent of segmentation).

    Returns: (epitope_residues_0based, bcell_score, epitope_detected)
    """
    if not scores:
        return [], 0.0, False

    score_map: dict[int, float] = {pos: s for pos, s in scores}  # 1-based → score

    # 1-based edit positions for comparison with IEDB output
    edit_1based = {p + 1 for p in edit_positions}

    # Mean score over the edit zone
    edit_scores = [score_map[p] for p in edit_1based if p in score_map]
    bcell_score = sum(edit_scores) / len(edit_scores) if edit_scores else 0.0

    # Find epitope segments (contiguous above-threshold runs ≥ MIN_LENGTH)
    epitope_positions: set[int] = set()  # 1-based positions in epitope segments
    current_run: list[int] = []
    for pos, score in sorted(scores):
        if score >= _THRESHOLD:
            current_run.append(pos)
        else:
            if len(current_run) >= _MIN_LENGTH:
                epitope_positions.update(current_run)
            current_run = []
    if len(current_run) >= _MIN_LENGTH:
        epitope_positions.update(current_run)

    # Check overlap with edit zone
    overlapping = epitope_positions & edit_1based
    epitope_detected = len(overlapping) > 0

    # Return 0-based residue positions (consistent with the rest of the pipeline)
    epitope_residues = sorted(p - 1 for p in overlapping)

    return epitope_residues, round(bcell_score, 4), epitope_detected


# ---------------------------------------------------------------------------
# Fallback result
# ---------------------------------------------------------------------------

def _conservative_fallback(patient_id: str, exc: Exception) -> BCellResult:
    logger.error(
        f"[{patient_id}] BepiPred call failed ({exc}); "
        "returning conservative fallback (epitope_detected=True)"
    )
    return BCellResult(
        epitope_residues=[],
        bcell_score=0.5,
        epitope_detected=True,  # conservative: assume risk when uncertain
    )


# ---------------------------------------------------------------------------
# Tool implementation
# ---------------------------------------------------------------------------

class BepiPredBCellTool(BCellTool):
    """
    Real B-cell epitope tool using BepiPred via the IEDB REST API.

    Submits the sequence window around the edit zone to the IEDB B-cell
    prediction endpoint and identifies linear epitope segments overlapping
    the edit positions.

    On any network or parse failure the tool returns a conservative fallback
    (epitope_detected=True, bcell_score=0.5) so the pipeline continues safely.
    """

    def predict(self, inp: PipelineInput, structural: StructuralResult) -> BCellResult:
        sequence_window, offset = _edit_window(inp.sequence, inp.edit_positions)

        logger.info(
            f"[{inp.patient_id}] BepiPred: submitting {len(sequence_window)}-aa window "
            f"(offset={offset}) to IEDB"
        )

        try:
            raw = _post_with_retry(
                _BCELL_URL,
                {
                    "method": "Bepipred",
                    "sequence_text": sequence_window,
                },
            )
        except requests.RequestException as exc:
            return _conservative_fallback(inp.patient_id, exc)
        except Exception as exc:
            return _conservative_fallback(inp.patient_id, exc)

        scores_in_window = _parse_scores(raw)
        if not scores_in_window:
            logger.warning(
                f"[{inp.patient_id}] BepiPred returned no rows; "
                "falling back to conservative result"
            )
            return _conservative_fallback(inp.patient_id, ValueError("empty response"))

        # IEDB positions are 1-based within the submitted window.
        # Translate edit_positions (0-based in full sequence) into the window frame.
        edit_in_window = [p - offset for p in inp.edit_positions if 0 <= p - offset < len(sequence_window)]

        epitope_residues_window, bcell_score, epitope_detected = _find_epitope_residues(
            scores_in_window, edit_in_window
        )

        # Translate back to full-sequence 0-based positions for consistency
        epitope_residues_full = [r + offset for r in epitope_residues_window]

        logger.info(
            f"[{inp.patient_id}] BepiPred: bcell_score={bcell_score:.3f} "
            f"epitope_detected={epitope_detected} "
            f"residues={epitope_residues_full}"
        )

        return BCellResult(
            epitope_residues=epitope_residues_full,
            bcell_score=bcell_score,
            epitope_detected=epitope_detected,
        )
