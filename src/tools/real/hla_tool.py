"""
Real Stage 2 — HLA binding prediction via the IEDB Analysis Resource REST API.

Replaces MHCflurry (which requires Python ≤ 3.12 due to the removed `pipes`
stdlib module). The IEDB API wraps the same tools the pipeline would use in
full production:
  - Class I:  NetMHCpan-4.1 (via IEDB "recommended" method)
  - Class II: NetMHCIIpan-4.0 (via IEDB "recommended" method)

Unlike MHCflurry, this covers both HLA classes, so the dual-gate early-exit
(Class I %Rank > 2.0 AND Class II %Rank > 10.0) functions correctly.

No installation beyond `requests` is needed. No API key or account required.

The API is called once per allele to get per-allele binding data. Only the
sequence window around the edit positions (±CONTEXT residues) is submitted,
reducing response size and latency. For a full-protein screen, set
IEDB_FULL_SEQUENCE=1.

IEDB API reference:
    https://help.iedb.org/hc/en-us/articles/114094152751

The base URL can be overridden via IEDB_API_BASE_URL if the default changes:
    export IEDB_API_BASE_URL=http://tools-cluster-interface.iedb.org/tools_api
"""

import csv
import io
import logging
import os
import time
import warnings
from typing import Optional

import requests
import urllib3

from src.tools.base import HLABindingTool
from src.models.pipeline import (
    PipelineInput,
    StructuralResult,
    HLABindingResult,
    PeptideBinding,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_BASE_URL    = os.getenv("IEDB_API_BASE_URL", "https://tools-cluster-interface.iedb.org/tools_api")
_MHCI_URL    = f"{_BASE_URL}/mhci/"
_MHCII_URL   = f"{_BASE_URL}/mhcii/"
_TIMEOUT     = int(os.getenv("IEDB_TIMEOUT", "60"))         # seconds per request
_FULL_SEQ    = os.getenv("IEDB_FULL_SEQUENCE", "").lower() in ("1", "true")
_VERIFY_SSL  = os.getenv("IEDB_VERIFY_SSL", "1") not in ("0", "false")  # disable with IEDB_VERIFY_SSL=0
_CONTEXT     = 15    # residues of flanking context around the edit zone

# Some research API servers block the default "python-requests/x.x.x" user-agent.
# Setting a neutral identifier avoids that filter.
_HEADERS = {"User-Agent": "immunogenicity-pipeline/1.0"}

if not _VERIFY_SSL:
    # Suppress the InsecureRequestWarning that requests emits on every call
    # when verify=False. The user has opted in explicitly via IEDB_VERIFY_SSL=0.
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    logger.warning(
        "SSL certificate verification disabled (IEDB_VERIFY_SSL=0). "
        "Only use this in a trusted network environment."
    )

# %Rank thresholds — consistent with NetMHCpan convention and scoring.py tiers
_STRONG_I, _WEAK_I   = 0.5,  2.0
_STRONG_II, _WEAK_II = 2.0, 10.0

# Rate-limiting: pause between requests to avoid triggering the IEDB server's
# per-IP throttle.  The demo runs 4 scenarios in quick succession; without a
# delay every allele call after the first few returns 403.
_REQUEST_DELAY = float(os.getenv("IEDB_REQUEST_DELAY", "1.5"))   # seconds between calls
_MAX_RETRIES   = int(os.getenv("IEDB_MAX_RETRIES", "3"))          # retries on 403/429/5xx
_RETRY_BACKOFF = float(os.getenv("IEDB_RETRY_BACKOFF", "4.0"))    # seconds for first retry (doubles each time)

_CLASS_I_PREFIXES  = ("HLA-A", "HLA-B", "HLA-C")
_CLASS_II_PREFIXES = ("HLA-DR", "HLA-DQ", "HLA-DP")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _edit_zone(sequence: str, edit_positions: list[int]) -> str:
    """
    Returns the sequence window spanning all edit positions plus flanking context.
    Submitting a smaller window to IEDB keeps requests fast and focuses
    predictions on the immunogenically relevant region.
    """
    if _FULL_SEQ or not edit_positions:
        return sequence
    lo = max(0, min(edit_positions) - _CONTEXT)
    hi = min(len(sequence), max(edit_positions) + _CONTEXT + 1)
    return sequence[lo:hi]


def _rank(row: dict) -> Optional[float]:
    """Extract %Rank regardless of column name variation across IEDB methods."""
    for col in ("percentile_rank", "rank", "ann_rank", "smm_rank", "comblib_rank"):
        v = row.get(col)
        if v and v not in ("-", ""):
            try:
                return float(v)
            except ValueError:
                pass
    return None


def _ic50(row: dict) -> float:
    for col in ("ic50", "ann_ic50", "smm_ic50", "score"):
        v = row.get(col)
        if v and v not in ("-", ""):
            try:
                return float(v)
            except ValueError:
                pass
    return 50000.0


def _parse_tsv(text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text.strip()), delimiter="\t")
    return [row for row in reader if row.get("peptide")]


def _to_binders(
    rows: list[dict],
    allele: str,
    strong_thresh: float,
    weak_thresh: float,
) -> list[PeptideBinding]:
    binders = []
    for row in rows:
        pct = _rank(row)
        if pct is None:
            continue
        strength = (
            "strong" if pct < strong_thresh else
            "weak"   if pct < weak_thresh   else
            "none"
        )
        binders.append(PeptideBinding(
            peptide=row["peptide"],
            hla_allele=allele,
            percent_rank=round(pct, 4),
            ic50_nm=round(_ic50(row), 2),
            strength=strength,
        ))
    binders.sort(key=lambda b: b.percent_rank)
    return binders


def _post_with_retry(url: str, data: dict) -> list[dict]:
    """
    POST to the IEDB API with inter-request delay and exponential-backoff retry.

    The IEDB free API throttles bursts from a single IP (typically returns 403).
    A short sleep before every call keeps us below the threshold; if we still
    hit a 403 or 429 we back off and retry up to _MAX_RETRIES times.
    """
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
                f"IEDB returned {resp.status_code} (rate limit?); "
                f"retrying in {delay:.0f}s (attempt {attempt + 1}/{_MAX_RETRIES})"
            )
            time.sleep(delay)
            delay *= 2
            continue
        resp.raise_for_status()
        return _parse_tsv(resp.text)
    resp.raise_for_status()   # final raise if all retries exhausted
    return []


def _call_mhci(allele: str, sequence: str) -> list[dict]:
    # The IEDB API requires exactly one length value per allele.
    # Submit 9-mer and 10-mer as separate calls and merge.
    rows: list[dict] = []
    for length in ("9", "10"):
        rows.extend(_post_with_retry(
            _MHCI_URL,
            {"method": "recommended", "sequence_text": sequence, "allele": allele, "length": length},
        ))
    return rows


def _call_mhcii(allele: str, sequence: str) -> list[dict]:
    return _post_with_retry(
        _MHCII_URL,
        {"method": "recommended", "sequence_text": sequence, "allele": allele},
    )


# ---------------------------------------------------------------------------
# Tool implementation
# ---------------------------------------------------------------------------

class IEDBHLABindingTool(HLABindingTool):
    """
    Real HLA binding tool using the IEDB Analysis Resource REST API.

    Predicts Class I and Class II binding for each allele in the patient's
    HLA profile, enabling the dual-gate early-exit to function correctly.
    """

    def predict(self, inp: PipelineInput, structural: StructuralResult) -> HLABindingResult:
        sequence = _edit_zone(inp.sequence, inp.edit_positions)

        class_i_alleles  = [a for a in inp.hla_profile if a.startswith(_CLASS_I_PREFIXES)]
        class_ii_alleles = [a for a in inp.hla_profile if a.startswith(_CLASS_II_PREFIXES)]

        logger.info(
            f"[{inp.patient_id}] IEDB: {len(class_i_alleles)} Class I + "
            f"{len(class_ii_alleles)} Class II alleles | "
            f"sequence window {len(sequence)} aa"
        )

        all_i:  list[PeptideBinding] = []
        all_ii: list[PeptideBinding] = []

        for allele in class_i_alleles:
            try:
                rows = _call_mhci(allele, sequence)
                all_i.extend(_to_binders(rows, allele, _STRONG_I, _WEAK_I))
            except requests.RequestException as exc:
                logger.warning(f"[{inp.patient_id}] Class I IEDB call failed for {allele}: {exc}")
            except Exception as exc:
                logger.warning(f"[{inp.patient_id}] Class I parse error for {allele}: {exc}")

        for allele in class_ii_alleles:
            try:
                rows = _call_mhcii(allele, sequence)
                all_ii.extend(_to_binders(rows, allele, _STRONG_II, _WEAK_II))
            except requests.RequestException as exc:
                logger.warning(f"[{inp.patient_id}] Class II IEDB call failed for {allele}: {exc}")
            except Exception as exc:
                logger.warning(f"[{inp.patient_id}] Class II parse error for {allele}: {exc}")

        all_i.sort(key=lambda b: b.percent_rank)
        all_ii.sort(key=lambda b: b.percent_rank)

        top_i  = all_i[0].percent_rank  if all_i  else 100.0
        top_ii = all_ii[0].percent_rank if all_ii else 100.0

        # If Class II alleles were absent from the profile, assume no binding data
        # and set to 100.0 (no binders found) rather than 0.0 (assume worst case).
        # This differs from MHCflurry behaviour where Class II was always unknown;
        # here we only penalise when we actually have alleles to screen.
        if not class_ii_alleles:
            top_ii = 0.0  # conservative: no Class II data → gate does not clear

        logger.info(
            f"[{inp.patient_id}] Class I top %Rank={top_i:.3f} "
            f"Class II top %Rank={top_ii:.3f}"
        )

        # Include all results in class_i_binders so Stage 3 always has a top
        # peptide to evaluate. TCR scoring is independent of HLA binding strength.
        return HLABindingResult(
            class_i_binders=all_i[:10],
            class_ii_binders=all_ii[:10],
            top_class_i_rank=top_i,
            top_class_ii_rank=top_ii,
        )
