"""
Real Stage 1 — Protein structure prediction via ESMFold.

ESMFold (Meta AI, Lin et al. 2023) predicts 3D protein structure in a single
forward pass through a 690M-parameter language model, with no multiple sequence
alignment step required. Two free API endpoints are supported:

  1. HuggingFace Inference API (recommended — more reliable, requires a free token)
       POST https://api-inference.huggingface.co/models/facebook/esmfold_v1
       Authorization: Bearer <HUGGINGFACE_API_KEY>
       Body: JSON {"inputs": "<sequence>"}
       Free token: https://huggingface.co/settings/tokens

  2. ESM Atlas (Meta, no auth required — may be overloaded / 504)
       POST https://api.esmatlas.com/foldSequence/v1/pdb/
       Content-Type: application/x-www-form-urlencoded
       Body: <sequence>

Selection logic (automatic):
  - HUGGINGFACE_API_KEY set → HuggingFace endpoint
  - Otherwise              → ESM Atlas (no auth)

Both return a PDB-format structure file. Per-residue pLDDT confidence scores are
stored in the B-factor column. SASA is calculated from the returned structure
using BioPython's ShrakeRupley algorithm.

Enable with:
    export ESMFOLD_ENABLED=1
    export HUGGINGFACE_API_KEY=hf_...   # recommended

Notes:
  - Sequences longer than ESMFOLD_MAX_LENGTH (default 400 aa) are truncated to the
    edit zone plus flanking context before submission.
  - If the API call fails for any reason, the tool returns a conservative fallback
    result (full surface exposure assumed) rather than raising — the pipeline's
    pLDDT retry loop will then treat it as low-confidence and skip to fallback mode.

API references:
  HuggingFace: https://huggingface.co/facebook/esmfold_v1
  ESM Atlas:   https://esmatlas.com/resources?action=fold
BioPython SASA: https://biopython.org/docs/latest/api/Bio.PDB.SASA.html
"""

import io
import logging
import os
import time
from typing import Literal

import requests
import urllib3

from src.tools.base import StructuralTool
from src.models.pipeline import PipelineInput, StructuralResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_HF_API_KEY  = os.getenv("HUGGINGFACE_API_KEY", "")
_HF_URL      = "https://api-inference.huggingface.co/models/facebook/esmfold_v1"
_ATLAS_URL   = "https://api.esmatlas.com/foldSequence/v1/pdb/"

_TIMEOUT     = int(os.getenv("ESMFOLD_TIMEOUT", "120"))          # seconds; fold takes ~10–60 s
_MAX_LENGTH  = int(os.getenv("ESMFOLD_MAX_LENGTH", "400"))        # aa; free API soft limit
_CONTEXT     = int(os.getenv("ESMFOLD_CONTEXT", "50"))            # flanking residues when truncating

_REQUEST_DELAY = float(os.getenv("ESMFOLD_REQUEST_DELAY", "1.0"))
_MAX_RETRIES   = int(os.getenv("ESMFOLD_MAX_RETRIES", "3"))
_RETRY_BACKOFF = float(os.getenv("ESMFOLD_RETRY_BACKOFF", "5.0"))

# Residues with mean SASA > 30 Å² over the edit zone are considered surface-exposed
_SASA_EXPOSED_THRESHOLD = 30.0

# ESM Atlas uses a CA cert with non-critical Basic Constraints — suppress the warning
# proactively since we always call it with verify=False.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ---------------------------------------------------------------------------
# Sequence preparation
# ---------------------------------------------------------------------------

def _prepare_sequence(sequence: str, edit_positions: list[int]) -> tuple[str, int]:
    """
    Truncate long sequences to the edit zone ± ESMFOLD_CONTEXT residues.

    Returns:
        (subsequence, offset) where offset is the 0-indexed start position in
        the original sequence, so that edit_positions can be re-mapped.
    """
    if len(sequence) <= _MAX_LENGTH:
        return sequence, 0

    lo = max(0, min(edit_positions) - _CONTEXT)
    hi = min(len(sequence), max(edit_positions) + _CONTEXT + 1)

    # If the window is still too long, centre on the midpoint of edit positions
    if hi - lo > _MAX_LENGTH:
        mid = (min(edit_positions) + max(edit_positions)) // 2
        lo  = max(0, mid - _MAX_LENGTH // 2)
        hi  = min(len(sequence), lo + _MAX_LENGTH)

    logger.warning(
        f"Sequence length {len(sequence)} exceeds ESMFOLD_MAX_LENGTH={_MAX_LENGTH}. "
        f"Submitting residues {lo}–{hi} (edit zone ±{_CONTEXT} context)."
    )
    return sequence[lo:hi], lo


# ---------------------------------------------------------------------------
# ESM Atlas API call with retry
# ---------------------------------------------------------------------------

def _build_endpoint(url: str) -> tuple[dict, dict, str]:
    """Return (headers, body_kwargs, label) for a given endpoint URL."""
    if "huggingface" in url and _HF_API_KEY:
        return (
            {
                "User-Agent":    "immunogenicity-pipeline/1.0",
                "Authorization": f"Bearer {_HF_API_KEY}",
                "Content-Type":  "application/json",
            },
            {},   # body filled in per-call
            "HuggingFace",
        )
    return (
        {
            "User-Agent":   "immunogenicity-pipeline/1.0",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        {},
        "ESM Atlas",
    )


def _post_endpoint(url: str, sequence: str, verify: bool) -> str:
    """
    POST to one endpoint with retry.  Returns PDB text on success.
    Raises requests.RequestException on all failures (caller decides whether to
    try the next endpoint).
    """
    is_hf = "huggingface" in url and bool(_HF_API_KEY)
    headers, _, label = _build_endpoint(url)
    body_kwargs: dict = (
        {"json": {"inputs": sequence}} if is_hf else {"data": sequence}
    )

    logger.info(f"ESMFold: trying {label} endpoint")
    time.sleep(_REQUEST_DELAY)

    delay = _RETRY_BACKOFF
    last_exc: Exception = RuntimeError("No attempts made")

    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = requests.post(
                url,
                headers=headers,
                timeout=_TIMEOUT,
                verify=verify,
                **body_kwargs,
            )
            if resp.status_code in (429, 503, 504) and attempt < _MAX_RETRIES:
                logger.warning(
                    f"ESMFold ({label}) returned {resp.status_code}; "
                    f"retrying in {delay:.0f}s (attempt {attempt + 1}/{_MAX_RETRIES})"
                )
                time.sleep(delay)
                delay *= 2
                continue
            resp.raise_for_status()
            # HuggingFace wraps the PDB in a JSON envelope on some model versions
            content_type = resp.headers.get("Content-Type", "")
            if "application/json" in content_type:
                payload = resp.json()
                if isinstance(payload, list) and payload:
                    return payload[0].get("generated_text", resp.text)
                if isinstance(payload, dict):
                    return payload.get("generated_text", resp.text)
            return resp.text
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES:
                logger.warning(
                    f"ESMFold ({label}) attempt {attempt + 1}/{_MAX_RETRIES} failed: {exc}"
                )
                time.sleep(delay)
                delay *= 2

    raise last_exc


def _call_esmfold(sequence: str) -> str:
    """
    Try each configured ESMFold endpoint in order, falling back to the next on
    network-level failures (DNS errors, connection refused, persistent 5xx).

    Order when HUGGINGFACE_API_KEY is set:  HuggingFace → ESM Atlas
    Order without a key:                    ESM Atlas only
    """
    # Build the ordered list of (url, verify_ssl) pairs to try
    endpoints: list[tuple[str, bool]] = []

    if _HF_API_KEY:
        endpoints.append((_HF_URL, True))    # HuggingFace cert is valid
    endpoints.append((_ATLAS_URL, False))     # ESM Atlas has a non-critical CA cert

    # If the user has pinned a custom URL, use only that
    custom_url = os.getenv("ESMFOLD_API_URL", "")
    if custom_url:
        verify = os.getenv("ESMFOLD_VERIFY_SSL", "1") not in ("0", "false")
        endpoints = [(custom_url, verify)]

    last_exc: Exception = RuntimeError("No ESMFold endpoints configured")

    for url, verify in endpoints:
        try:
            return _post_endpoint(url, sequence, verify)
        except requests.RequestException as exc:
            logger.warning(f"ESMFold endpoint {url} failed: {exc} — trying next")
            last_exc = exc

    raise last_exc


# ---------------------------------------------------------------------------
# PDB parsing: pLDDT and SASA extraction
# ---------------------------------------------------------------------------

def _parse_pdb(pdb_text: str, edit_positions: list[int], offset: int) -> tuple[float, float]:
    """
    Parse ESMFold PDB output using BioPython.

    Args:
        pdb_text:       PDB-format string returned by the ESMFold API.
        edit_positions: 0-indexed residue positions in the *original* sequence.
        offset:         Start position of the submitted subsequence; used to
                        re-map edit_positions into the PDB's 1-indexed residue IDs.

    Returns:
        (mean_plddt, mean_sasa_angstrom2) averaged over the edit zone residues.

    ESMFold writes per-residue pLDDT into the B-factor column (one value per
    atom; all atoms in a residue share the same B-factor).  SASA is computed
    with the Shrake–Rupley rolling-sphere algorithm.
    """
    from Bio.PDB import PDBParser
    from Bio.PDB.SASA import ShrakeRupley

    parser   = PDBParser(QUIET=True)
    structure = parser.get_structure("esmfold", io.StringIO(pdb_text))

    model  = structure[0]
    chain  = next(model.get_chains())
    residues = list(chain.get_residues())

    # pLDDT: first atom B-factor of each residue (0-indexed key = PDB resnum - 1)
    # ESM Atlas stores pLDDT in the 0–1 range; AlphaFold / HuggingFace use 0–100.
    # Detect by checking whether all B-factors are ≤ 1.0 and scale accordingly.
    plddt_by_res: dict[int, float] = {}
    for res in residues:
        seq_idx = res.get_id()[1] - 1   # PDB is 1-indexed
        atoms   = list(res.get_atoms())
        if atoms:
            plddt_by_res[seq_idx] = atoms[0].get_bfactor()

    if plddt_by_res and max(plddt_by_res.values()) <= 1.0:
        plddt_by_res = {k: v * 100 for k, v in plddt_by_res.items()}

    # SASA via ShrakeRupley (residue level)
    sr = ShrakeRupley()
    sr.compute(structure, level="R")
    sasa_by_res: dict[int, float] = {}
    for res in residues:
        seq_idx = res.get_id()[1] - 1
        sasa_by_res[seq_idx] = res.sasa  # type: ignore[attr-defined]

    # Re-map original edit_positions into the submitted subsequence coordinate space
    local_positions = [p - offset for p in edit_positions]
    valid = [p for p in local_positions if p in plddt_by_res]

    if not valid:
        logger.warning(
            "None of the edit positions mapped to parsed PDB residues — "
            "returning conservative fallback values."
        )
        return 45.0, 999.0

    mean_plddt = sum(plddt_by_res[p] for p in valid) / len(valid)
    mean_sasa  = sum(sasa_by_res.get(p, 999.0) for p in valid) / len(valid)

    return mean_plddt, mean_sasa


# ---------------------------------------------------------------------------
# Tool implementation
# ---------------------------------------------------------------------------

class ESMFoldStructuralTool(StructuralTool):
    """
    Real structural tool using ESMFold via the ESM Atlas public REST API.

    Submits the protein sequence (truncated to edit zone ± context if long),
    parses the PDB for per-residue pLDDT and SASA, and returns a StructuralResult
    keyed on the edit zone residues.

    On any failure (network error, parse error) the tool returns a conservative
    result with edit_zone_exposed=True, which will trigger the pipeline's pLDDT
    retry loop and ultimately the fallback path.
    """

    def predict(self, inp: PipelineInput, fallback_mode: bool = False) -> StructuralResult:
        if fallback_mode:
            logger.info(
                f"[{inp.patient_id}] ESMFold: fallback mode — "
                "skipping API call, assuming full surface exposure"
            )
            return StructuralResult(
                plddt_score=45.0,
                sasa_edit_zone=999.0,
                edit_zone_exposed=True,
                confidence="low",
                fallback_mode=True,
            )

        sequence, offset = _prepare_sequence(inp.sequence, inp.edit_positions)

        logger.info(
            f"[{inp.patient_id}] ESMFold: submitting {len(sequence)} aa "
            f"(original {len(inp.sequence)} aa, offset={offset}, "
            f"edit positions={inp.edit_positions})"
        )

        # --- API call -------------------------------------------------------
        try:
            pdb_text = _call_esmfold(sequence)
        except Exception as exc:
            logger.warning(
                f"[{inp.patient_id}] ESMFold API failed: {exc} — "
                "returning conservative fallback result"
            )
            return StructuralResult(
                plddt_score=45.0,
                sasa_edit_zone=999.0,
                edit_zone_exposed=True,
                confidence="low",
                fallback_mode=True,
            )

        # --- PDB parsing ----------------------------------------------------
        try:
            mean_plddt, mean_sasa = _parse_pdb(pdb_text, inp.edit_positions, offset)
        except Exception as exc:
            logger.warning(
                f"[{inp.patient_id}] PDB parsing failed: {exc} — "
                "returning conservative fallback result"
            )
            return StructuralResult(
                plddt_score=45.0,
                sasa_edit_zone=999.0,
                edit_zone_exposed=True,
                confidence="low",
                fallback_mode=True,
            )

        # --- Interpret results ----------------------------------------------
        confidence: Literal["high", "medium", "low"]
        if mean_plddt >= 70:
            confidence = "high"
        elif mean_plddt >= 50:
            confidence = "medium"
        else:
            confidence = "low"

        exposed = mean_sasa > _SASA_EXPOSED_THRESHOLD

        logger.info(
            f"[{inp.patient_id}] ESMFold: pLDDT={mean_plddt:.1f} ({confidence}) "
            f"SASA={mean_sasa:.1f} Å²  exposed={exposed}"
        )

        return StructuralResult(
            plddt_score=round(mean_plddt, 2),
            sasa_edit_zone=round(mean_sasa, 2),
            edit_zone_exposed=exposed,
            confidence=confidence,
            fallback_mode=False,
        )
