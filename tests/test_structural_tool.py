"""
Offline tests for src/tools/real/structural_tool.py.

No network calls are made — the HTTP layer is patched with a known PDB
fixture that has controlled B-factor and coordinate values so we can assert
exact pLDDT, SASA, confidence tier, and exposure outputs.

Run:
    uv run python tests/test_structural_tool.py
    uv run python -m pytest tests/test_structural_tool.py -v
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Minimal polyalanine PDB fixture
#
# Three ALA residues with backbone + CB atoms spread ~8 Å apart along the
# x-axis so every residue is fully solvent-exposed (SASA >> 30 Å²).
#
# B-factor values use ESM Atlas's 0–1 convention:
#   residue 1 (seq_idx=0): 0.88 → 88.0  (high)
#   residue 2 (seq_idx=1): 0.61 → 61.0  (medium)
#   residue 3 (seq_idx=2): 0.44 → 44.0  (low)
# ---------------------------------------------------------------------------

_PDB_FIXTURE = """\
ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00  0.88           N
ATOM      2  CA  ALA A   1       1.458   0.000   0.000  1.00  0.88           C
ATOM      3  C   ALA A   1       2.009   1.420   0.000  1.00  0.88           C
ATOM      4  O   ALA A   1       1.250   2.330  -0.390  1.00  0.88           O
ATOM      5  CB  ALA A   1       1.988  -0.772  -1.232  1.00  0.88           C
ATOM      6  N   ALA A   2       8.340   1.584   0.000  1.00  0.61           N
ATOM      7  CA  ALA A   2       9.028   2.866   0.000  1.00  0.61           C
ATOM      8  C   ALA A   2      10.547   2.761  -0.044  1.00  0.61           C
ATOM      9  O   ALA A   2      11.221   3.783  -0.205  1.00  0.61           O
ATOM     10  CB  ALA A   2       8.579   3.688   1.200  1.00  0.61           C
ATOM     11  N   ALA A   3      16.138   1.572  -0.006  1.00  0.44           N
ATOM     12  CA  ALA A   3      17.587   1.393  -0.022  1.00  0.44           C
ATOM     13  C   ALA A   3      18.126   0.877   1.308  1.00  0.44           C
ATOM     14  O   ALA A   3      19.316   0.595   1.386  1.00  0.44           O
ATOM     15  CB  ALA A   3      18.132   2.742  -0.491  1.00  0.44           C
END
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_input(edit_positions: list[int]):
    from src.models.pipeline import PipelineInput
    return PipelineInput(
        patient_id="TEST",
        sequence="ALA" * 3,   # not used for parsing, just needs to be non-empty
        edit_positions=edit_positions,
        hla_profile=["HLA-A*02:01"],
    )


def _mock_response(pdb_text: str) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.text = pdb_text
    resp.headers = {"Content-Type": "text/plain"}
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_plddt_scale_normalised():
    """ESM Atlas 0–1 B-factors are scaled to 0–100."""
    from src.tools.real.structural_tool import _parse_pdb
    mean_plddt, _ = _parse_pdb(_PDB_FIXTURE, edit_positions=[0], offset=0)
    assert 80 < mean_plddt < 95, f"expected ~88.0, got {mean_plddt}"


def test_plddt_high_confidence():
    """Edit at residue 0 (B-factor 0.88) → confidence='high'."""
    from src.tools.real.structural_tool import ESMFoldStructuralTool

    with patch("src.tools.real.structural_tool._post_endpoint", return_value=_PDB_FIXTURE):
        result = ESMFoldStructuralTool().predict(_make_input([0]))

    assert result.confidence == "high", f"got {result.confidence}"
    assert 80 < result.plddt_score < 95
    assert result.fallback_mode is False


def test_plddt_medium_confidence():
    """Edit at residue 1 (B-factor 0.61) → confidence='medium'."""
    from src.tools.real.structural_tool import ESMFoldStructuralTool

    with patch("src.tools.real.structural_tool._post_endpoint", return_value=_PDB_FIXTURE):
        result = ESMFoldStructuralTool().predict(_make_input([1]))

    assert result.confidence == "medium", f"got {result.confidence}"
    assert 50 < result.plddt_score < 70


def test_plddt_low_confidence():
    """Edit at residue 2 (B-factor 0.44) → confidence='low'."""
    from src.tools.real.structural_tool import ESMFoldStructuralTool

    with patch("src.tools.real.structural_tool._post_endpoint", return_value=_PDB_FIXTURE):
        result = ESMFoldStructuralTool().predict(_make_input([2]))

    assert result.confidence == "low", f"got {result.confidence}"
    assert result.plddt_score < 50


def test_sasa_exposed():
    """All residues are spread far apart → each should be surface-exposed (SASA > 30 Å²)."""
    from src.tools.real.structural_tool import ESMFoldStructuralTool

    with patch("src.tools.real.structural_tool._post_endpoint", return_value=_PDB_FIXTURE):
        result = ESMFoldStructuralTool().predict(_make_input([0, 1, 2]))

    assert result.edit_zone_exposed is True, f"expected exposed, SASA={result.sasa_edit_zone}"
    assert result.sasa_edit_zone > 30


def test_fallback_mode_skips_api():
    """fallback_mode=True must not call the API at all."""
    from src.tools.real.structural_tool import ESMFoldStructuralTool

    with patch("src.tools.real.structural_tool._post_endpoint") as mock_post:
        result = ESMFoldStructuralTool().predict(_make_input([0]), fallback_mode=True)

    mock_post.assert_not_called()
    assert result.fallback_mode is True
    assert result.edit_zone_exposed is True   # conservative assumption


def test_api_failure_returns_fallback():
    """Any network error must degrade gracefully to a conservative fallback result."""
    import requests
    from src.tools.real.structural_tool import ESMFoldStructuralTool

    with patch(
        "src.tools.real.structural_tool._post_endpoint",
        side_effect=requests.ConnectionError("simulated network failure"),
    ):
        result = ESMFoldStructuralTool().predict(_make_input([0]))

    assert result.fallback_mode is True
    assert result.edit_zone_exposed is True
    assert result.confidence == "low"


# ---------------------------------------------------------------------------
# Run directly (no pytest required)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_plddt_scale_normalised,
        test_plddt_high_confidence,
        test_plddt_medium_confidence,
        test_plddt_low_confidence,
        test_sasa_exposed,
        test_fallback_mode_skips_api,
        test_api_failure_returns_fallback,
    ]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception as exc:
            print(f"  FAIL  {t.__name__}: {exc}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
