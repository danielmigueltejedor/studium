"""Regression tests for structured problem verification."""

from copy import deepcopy

from studium.authoring.problem_verification import verify_problem_dimensions
from studium.verification.model import VerificationStatus


def _continuity_solution():
    return {
        "given": [
            {"symbol": "V1", "value": "1", "unit": "m/s"},
            {"symbol": "D1", "value": "0.2", "unit": "m"},
            {"symbol": "D2", "value": "0.1", "unit": "m"},
        ],
        "model": [
            {"symbolic": "V1*(D1*D1)/(D2*D2)"},
        ],
    }


def test_continuity_equation_has_velocity_dimensions():
    result = verify_problem_dimensions(
        _continuity_solution(),
        expected_unit="m/s",
    )

    assert result.status is VerificationStatus.DIMENSIONALLY_VERIFIED
    assert result.ok


def test_incorrect_expected_unit_fails():
    result = verify_problem_dimensions(
        _continuity_solution(),
        expected_unit="Pa",
    )

    assert result.status is VerificationStatus.FAILED
    assert not result.ok


def test_incompatible_addition_fails():
    solution = _continuity_solution()
    solution["model"][0]["symbolic"] = "V1 + D1"

    result = verify_problem_dimensions(
        solution,
        expected_unit="m/s",
    )

    assert result.status is VerificationStatus.FAILED


def test_missing_expected_unit_is_unverified():
    result = verify_problem_dimensions(_continuity_solution())

    assert result.status is VerificationStatus.UNVERIFIED
    assert "dimensions" in result.outputs


def test_missing_quantity_unit_is_unverified():
    solution = _continuity_solution()
    solution["given"][0].pop("unit")

    result = verify_problem_dimensions(
        solution,
        expected_unit="m/s",
    )

    assert result.status is VerificationStatus.UNVERIFIED


def test_undefined_symbol_is_unverified():
    solution = _continuity_solution()
    solution["model"][0]["symbolic"] = "V1 * unknown"

    result = verify_problem_dimensions(
        solution,
        expected_unit="m/s",
    )

    assert result.status is VerificationStatus.UNVERIFIED


def test_multiple_models_are_not_silently_accepted():
    solution = _continuity_solution()
    solution["model"].append({"symbolic": "V1 * D1"})

    result = verify_problem_dimensions(
        solution,
        expected_unit="m/s",
    )

    assert result.status is VerificationStatus.UNVERIFIED


def test_physical_validity_is_not_implied():
    solution = _continuity_solution()
    solution["model"][0]["symbolic"] = "2 * V1"

    result = verify_problem_dimensions(
        solution,
        expected_unit="m/s",
    )

    assert result.status is VerificationStatus.DIMENSIONALLY_VERIFIED
    assert any("physical validity" in x for x in result.limitations)


def test_verification_does_not_modify_solution():
    solution = _continuity_solution()
    original = deepcopy(solution)

    verify_problem_dimensions(solution, expected_unit="m/s")

    assert solution == original


def test_numeric_continuity_reproduces_four_metres_per_second():
    from studium.authoring.problem_verification import verify_problem_numeric

    result = verify_problem_numeric(
        _continuity_solution(),
        expected_value=4.0,
        expected_unit="m/s",
    )

    assert result.status is VerificationStatus.COMPUTATION_REPRODUCED
    assert result.outputs["calculated_base_value"] == 4.0


def test_numeric_incorrect_result_fails():
    from studium.authoring.problem_verification import verify_problem_numeric

    result = verify_problem_numeric(
        _continuity_solution(),
        expected_value=2.0,
        expected_unit="m/s",
    )

    assert result.status is VerificationStatus.FAILED


def test_numeric_unit_conversion():
    from studium.authoring.problem_verification import verify_problem_numeric

    solution = _continuity_solution()

    solution["given"][1]["value"] = "20"
    solution["given"][1]["unit"] = "cm"

    solution["given"][2]["value"] = "10"
    solution["given"][2]["unit"] = "cm"

    result = verify_problem_numeric(
        solution,
        expected_value=400.0,
        expected_unit="cm/s",
    )

    assert result.status is VerificationStatus.COMPUTATION_REPRODUCED


def test_numeric_missing_value_is_unverified():
    from studium.authoring.problem_verification import verify_problem_numeric

    solution = _continuity_solution()
    solution["given"][0].pop("value")

    result = verify_problem_numeric(
        solution,
        expected_value=4.0,
        expected_unit="m/s",
    )

    assert result.status is VerificationStatus.UNVERIFIED


def test_numeric_invalid_output_unit_fails():
    from studium.authoring.problem_verification import verify_problem_numeric

    result = verify_problem_numeric(
        _continuity_solution(),
        expected_value=4.0,
        expected_unit="Pa",
    )

    assert result.status is VerificationStatus.FAILED


def test_numeric_match_does_not_claim_physical_validity():
    from studium.authoring.problem_verification import verify_problem_numeric

    solution = _continuity_solution()
    solution["model"][0]["symbolic"] = "2 * V1"

    result = verify_problem_numeric(
        solution,
        expected_value=2.0,
        expected_unit="m/s",
    )

    assert result.status is VerificationStatus.COMPUTATION_REPRODUCED
    assert any("physical validity" in x for x in result.limitations)
