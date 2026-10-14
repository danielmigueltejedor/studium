"""Regression tests for non-destructive substitution auditing."""

from copy import deepcopy

from test_substitution_provenance import _example

from studium.authoring.problems import _solution
from studium.authoring.substitution_audit import audit_substitution


def test_current_generated_substitution_matches():
    solution, error = _solution(_example())

    assert error is None
    assert solution is not None

    result = audit_substitution(solution)

    assert result["status"] == "match"
    assert result["origin"] == "generated"


def test_different_generated_substitution_is_detected_without_rewriting():
    solution, error = _solution(_example())

    assert error is None
    assert solution is not None

    solution["substitution"] = r"\frac{0.2}{0.1}"
    before = deepcopy(solution)

    result = audit_substitution(solution)

    assert result["status"] == "different"
    assert result["origin"] == "generated"
    assert result["candidate"] != result["stored"]
    assert solution == before


def test_legacy_manual_substitution_is_not_rewritten():
    solution = _example()
    solution["substitution"] = r"\frac{1}{2}"
    before = deepcopy(solution)

    result = audit_substitution(solution)

    assert result["status"] == "different"
    assert result["origin"] == "unknown"
    assert solution == before


def test_missing_substitution_is_reported():
    result = audit_substitution(_example())

    assert result["status"] == "missing"


def test_missing_model_is_inconclusive():
    result = audit_substitution({
        "substitution": r"\frac{1}{2}",
    })

    assert result["status"] == "inconclusive"
