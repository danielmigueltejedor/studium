"""Tests for the read-only stored problem scientific review."""

from copy import deepcopy
from pathlib import Path

from pytest import MonkeyPatch

from studium.authoring.problem_review import review_stored_problem
from studium.authoring.problems import _solution
from studium.mcp.catalog import tool_names


def _stored_problem():
    raw_solution = {
        "given": [
            {"symbol": "V1", "value": "1", "unit": "m/s"},
            {"symbol": "D1", "value": "0.2", "unit": "m"},
            {"symbol": "D2", "value": "0.1", "unit": "m"},
        ],
        "model": [
            {
                "name": "Continuity",
                "latex": r"V_2 = V_1 (D_1/D_2)^2",
                "symbolic": "V1*(D1*D1)/(D2*D2)",
            },
        ],
    }

    normalized, error = _solution(raw_solution)

    assert error is None
    assert normalized is not None

    return {
        "id": "PRB-0021",
        "kind": "numeric",
        "status": "two_witnesses",
        "solution": normalized,
    }


def _mock_problems(monkeypatch: MonkeyPatch, problems: list[dict]):
    monkeypatch.setattr(
        "studium.authoring.problem_review.list_problems",
        lambda root: {"status": "ok", "problems": problems},
    )


def test_scientific_review_is_registered_in_mcp():
    assert "studium_problem_scientific_review" in tool_names()


def test_stored_problem_returns_scientific_report(monkeypatch: MonkeyPatch):
    problem = _stored_problem()
    original = deepcopy(problem)

    _mock_problems(monkeypatch, [problem])

    result = review_stored_problem(
        Path("."),
        problem_id="PRB-0021",
        expected_value=4.0,
        expected_unit="m/s",
    )

    assert result["status"] == "ok"
    assert result["problem_id"] == "PRB-0021"
    assert result["advisory"] is True
    assert result["stored_content_modified"] is False

    report = result["report"]
    assert report["status"] == "UNVERIFIED"

    checks = report["outputs"]["checks"]

    assert checks["dimensional"]["status"] == "DIMENSIONALLY_VERIFIED"
    assert checks["numeric"]["status"] == "COMPUTATION_REPRODUCED"
    assert checks["substitution"]["status"] == "match"

    assert problem == original


def test_missing_problem_is_rejected(monkeypatch: MonkeyPatch):
    _mock_problems(monkeypatch, [])

    result = review_stored_problem(
        Path("."),
        problem_id="PRB-9999",
    )

    assert result["status"] == "problem.not_found"


def test_missing_id_is_rejected():
    result = review_stored_problem(
        Path("."),
        problem_id=None,
    )

    assert result["status"] == "mcp.invalid_input"


def test_expected_value_requires_unit():
    result = review_stored_problem(
        Path("."),
        problem_id="PRB-0021",
        expected_value=4.0,
    )

    assert result["status"] == "mcp.invalid_input"


def test_nonfinite_expected_value_is_rejected():
    result = review_stored_problem(
        Path("."),
        problem_id="PRB-0021",
        expected_value=float("nan"),
        expected_unit="m/s",
    )

    assert result["status"] == "mcp.invalid_input"


def test_rust_problem_is_not_scientifically_reviewed(monkeypatch: MonkeyPatch):
    _mock_problems(
        monkeypatch,
        [{"id": "PRB-0001", "kind": "rust", "status": "checked"}],
    )

    result = review_stored_problem(
        Path("."),
        problem_id="PRB-0001",
    )

    assert result["status"] == "problem.unsupported_kind"


def test_review_without_expected_value_remains_unverified(
    monkeypatch: MonkeyPatch,
):
    _mock_problems(monkeypatch, [_stored_problem()])

    result = review_stored_problem(
        Path("."),
        problem_id="PRB-0021",
    )

    assert result["status"] == "ok"

    checks = result["report"]["outputs"]["checks"]

    assert checks["numeric"]["status"] == "UNVERIFIED"
    assert result["report"]["status"] == "UNVERIFIED"
