"""Point checks preserve the original domain and limits preserve their direction."""

import pytest

from studium.mcp.server import dispatch, open_workspace
from studium.verification import (
    VerificationStatus,
    verify_equation,
    verify_limit,
    verify_numeric_cross_check,
    verify_substitution,
)


@pytest.mark.parametrize("left,right", [("1/x", "1/x"), ("x/x", "1"), ("log(x)", "log(x)"), ("x**-1", "x**-1")])
def test_an_equation_cannot_verify_an_undefined_solution(left, right):
    result = verify_equation(left, right, solution={"x": "0"})
    assert result.status == VerificationStatus.FAILED
    assert not result.ok
    assert result.inputs == {"left": left, "right": right, "solution": {"x": "0"}}
    assert "undefined" in result.detail


@pytest.mark.parametrize("expression", ["x/x", "0*(1/x)", "(x*x)/x", "x**-1-x**-1", "log(x)-log(x)"])
def test_replayed_values_do_not_cancel_singularities(expression):
    result = verify_substitution(expression, values={"x": 0}, claimed=1)
    assert result.status == VerificationStatus.FAILED
    assert "undefined" in result.detail


def test_numeric_samples_refuse_original_singularities():
    result = verify_numeric_cross_check("x/x", "1", symbols={"x"}, samples=[{"x": 0}])
    assert result.status == VerificationStatus.FAILED
    assert "undefined" in result.detail
    assert verify_numeric_cross_check("x/x", "1", symbols={"x"}, samples=[{"x": 2}]).ok


def test_removable_singularity_does_not_prevent_a_limit():
    assert verify_limit("sin(x)/x", variable="x", point="0", claimed="1").ok
    assert verify_limit("x/x", variable="x", point="0", claimed="1").ok


def test_finite_unsuffixed_limit_checks_both_directions():
    result = verify_limit("abs(x)/x", variable="x", point="0", claimed="1")
    assert result.status == VerificationStatus.UNVERIFIED
    assert not result.ok
    assert result.inputs["point"] == "0"
    assert verify_limit("abs(x)/x", variable="x", point="0+", claimed="1").ok
    assert verify_limit("abs(x)/x", variable="x", point="0-", claimed="-1").ok
    assert not verify_limit("abs(x)/x", variable="x", point="0-", claimed="1").ok


def test_equation_checks_keep_defined_symbolic_families_and_complex_values():
    assert verify_equation("1/x", "1/x", solution={"x": "2"}).ok
    conditional = verify_equation("x/x", "1", solution={"x": "y"}, symbols={"y"})
    assert conditional.ok
    assert any("domain" in item for item in conditional.limitations)
    assert verify_equation("x**2", "-1", solution={"x": "sqrt(-1)"}).ok


def test_equation_also_checks_original_solution_expression():
    result = verify_equation("x", "1", solution={"x": "y/y", "y": "0"})
    assert result.status == VerificationStatus.FAILED
    assert "undefined" in result.detail


@pytest.mark.parametrize("solution", [{"x": "y", "y": "0"}, {"x": "y", "y": "x"}, {"x": "x"}])
def test_cross_bound_solution_mappings_are_explicitly_undecided(solution):
    result = verify_equation("x/x", "1", solution=solution)
    assert result.status == VerificationStatus.UNVERIFIED
    assert "solution assignments" in result.detail


def test_mcp_persists_rejected_domain_and_undecided_limit(tmp_path):
    session = open_workspace(str(tmp_path))
    assert dispatch("studium_project_create", {"slug": "domain", "topic": "Mathematics"}, session=session)["status"] == "created"
    for arguments, expected in (
        ({"kind": "equation", "left": "x/x", "right": "1", "solution": {"x": "0"}}, "FAILED"),
        ({"kind": "limit", "expression": "abs(x)/x", "variable": "x", "point": "0", "claimed": "1"}, "UNVERIFIED"),
    ):
        result = dispatch("studium_math_verify", arguments, session=session)
        assert result["status"] == "recorded_but_not_accepted"
        assert result["accepted"] is False
        assert result["verification_status"] == expected
        assert result["verification"]["inputs"]
        assert result["released"] is False
