"""Regression tests for unified scientific problem reports."""

from copy import deepcopy

from studium.authoring.problem_report import verify_problem_report
from studium.authoring.problems import _solution
from studium.verification.model import VerificationStatus


def _example():
    solution = {
        "given": [
            {"symbol": "V1", "value": "1", "unit": "m/s"},
            {"symbol": "D1", "value": "0.2", "unit": "m"},
            {"symbol": "D2", "value": "0.1", "unit": "m"},
        ],
        "model": [
            {
                "name": "Continuity equation",
                "latex": r"V_2 = V_1 \left(\frac{D_1}{D_2}\right)^2",
                "symbolic": "V1*(D1*D1)/(D2*D2)",
            },
        ],
    }

    normalized, error = _solution(solution)

    assert error is None
    assert normalized is not None

    return normalized


def test_correct_calculation_does_not_prove_physics():
    report = verify_problem_report(
        _example(),
        expected_value=4.0,
        expected_unit="m/s",
    )

    checks = report.outputs["checks"]

    assert report.status is VerificationStatus.UNVERIFIED
    assert checks["dimensional"]["status"] == "DIMENSIONALLY_VERIFIED"
    assert checks["numeric"]["status"] == "COMPUTATION_REPRODUCED"
    assert checks["substitution"]["status"] == "match"
    assert report.outputs["human_review_required"] is True


def test_incorrect_numeric_result_fails():
    report = verify_problem_report(
        _example(),
        expected_value=2.0,
        expected_unit="m/s",
    )

    assert report.status is VerificationStatus.FAILED
    assert report.outputs["checks"]["numeric"]["status"] == "FAILED"


def test_incorrect_dimensions_fail():
    report = verify_problem_report(
        _example(),
        expected_value=4.0,
        expected_unit="Pa",
    )

    assert report.status is VerificationStatus.FAILED
    assert report.outputs["checks"]["dimensional"]["status"] == "FAILED"


def test_declared_assumptions_do_not_prove_physics():
    solution = _example()
    solution["assumptions"] = [
        "Steady flow",
        "Incompressible fluid",
    ]

    report = verify_problem_report(
        solution,
        expected_value=4.0,
        expected_unit="m/s",
    )

    assert report.status is VerificationStatus.UNVERIFIED
    assert len(report.assumptions) == 2

    assert any(
        "not been independently verified" in issue
        for issue in report.outputs["issues"]
    )


def test_stale_substitution_requires_review_without_numeric_failure():
    solution = _example()
    solution["substitution"] = r"\frac{0.2}{0.1}"
    solution.pop("substitution_origin", None)

    report = verify_problem_report(
        solution,
        expected_value=4.0,
        expected_unit="m/s",
    )

    checks = report.outputs["checks"]

    assert report.status is VerificationStatus.UNVERIFIED
    assert checks["numeric"]["status"] == "COMPUTATION_REPRODUCED"
    assert checks["substitution"]["status"] == "different"
    assert checks["substitution"]["origin"] == "unknown"


def test_missing_expected_result_is_not_silently_verified():
    report = verify_problem_report(
        _example(),
        expected_unit="m/s",
    )

    assert report.status is VerificationStatus.UNVERIFIED
    assert report.outputs["checks"]["numeric"]["status"] == "UNVERIFIED"


def test_report_does_not_modify_stored_content():
    solution = _example()
    original = deepcopy(solution)

    verify_problem_report(
        solution,
        expected_value=4.0,
        expected_unit="m/s",
    )

    assert solution == original
