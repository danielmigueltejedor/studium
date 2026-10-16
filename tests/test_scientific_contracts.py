"""Synthetic scientific counterexamples; no course material or invented evidence."""

from copy import deepcopy

import pytest


def assess(contract):
    from studium.verification.scientific import assess_contract

    return assess_contract(contract)


def contract(checks, *, bindings=None, assumptions=None, requires=None, variables=None):
    return {
        "variables": variables or {"x": "dimensionless", "y": "dimensionless", "z": "dimensionless"},
        "bindings": bindings or {},
        "assumptions": assumptions or [],
        "equations": [],
        "derivations": [],
        "representations": [{"record": "PAR-1", "role": "theory", "requires": requires or [], "checks": checks}],
    }


def outcomes(report):
    return [item["status"] for item in report["checks"]]


def aerodynamic_contract():
    data = contract(
        [{"kind": "identity", "left": "K*CL2", "right": "CD0"}],
        variables=dict.fromkeys(("K", "CL2", "CD0", "ei", "AR", "cd2"), "dimensionless"),
        bindings={"K": "1/(pi*ei*AR)+cd2", "CL2": "CD0/K"},
    )
    for role in ("derivation", "example", "self_check", "problem", "solution", "appendix"):
        data["representations"].append(
            {
                "record": f"PAR-{role}",
                "role": role,
                "requires": [],
                "checks": [{"kind": "identity", "left": "CL2/(pi*ei*AR)", "right": "CD0"}],
            }
        )
    return data


def test_total_quadratic_drag_is_not_isolated_induced_drag_across_book():
    report = assess(aerodynamic_contract())
    assert outcomes(report) == ["SYMBOLICALLY_VERIFIED", *(["FAILED"] * 6)]
    assert all("cd2" in item["detail"] for item in report["checks"][1:])
    assert report["verification"]["expert_review"] == "PENDING"
    assert report["scientific_validity"] == "not_established"


def test_induced_drag_equality_requires_constant_profile_drag():
    data = aerodynamic_contract()
    data["bindings"]["cd2"] = "0"
    assert set(outcomes(assess(data))) == {"SYMBOLICALLY_VERIFIED"}


@pytest.mark.parametrize(
    "expression,bindings",
    [
        ("x/y", {"y": "0"}),
        ("x/x", {"x": "0"}),
        ("x**(-1)", {"x": "0"}),
    ],
)
def test_original_expression_is_undefined_even_after_cancellation(expression, bindings):
    report = assess(contract([{"kind": "defined", "expression": expression}], bindings=bindings))
    assert outcomes(report) == ["FAILED"]


def test_reynolds_similarity_retains_viscosity_ratio():
    data = contract(
        [{"kind": "identity", "left": "U1*(nu2/nu1)*(d1/d2)", "right": "U1*d1/d2"}],
        variables=dict.fromkeys(("U1", "nu1", "nu2", "d1", "d2"), "dimensionless"),
    )
    assert outcomes(assess(data)) == ["FAILED"]
    data["bindings"] = {"nu2": "nu1"}
    assert outcomes(assess(data)) == ["SYMBOLICALLY_VERIFIED"]


def test_inclined_distance_is_not_vertical_depth():
    data = contract(
        [{"kind": "identity", "left": "s*sin(theta)", "right": "s"}],
        variables={"s": "m", "theta": "dimensionless"},
        bindings={"theta": "pi/6"},
    )
    assert outcomes(assess(data)) == ["FAILED"]


def test_continuity_and_acceleration_do_not_prove_pressure_compatibility():
    # u=(y,0,0), acceleration=0, constant rho/mu, body force=(0,x,0).
    # div(u)=0, laplacian(u)=0, but required grad(p)=(0,rho*x,0) has curl != 0.
    data = contract(
        [
            {"kind": "identity", "left": "0", "right": "0"},
            {"kind": "gradient", "coordinates": ["x", "y", "z"], "components": ["0", "x", "0"]},
        ]
    )
    assert outcomes(assess(data)) == ["SYMBOLICALLY_VERIFIED", "FAILED"]
    data["representations"][0]["checks"][1]["components"] = ["2*x", "2*y", "2*z"]
    result = assess(data)["checks"][1]
    assert result["status"] == "MODEL_CONSISTENT_UNDER_ASSUMPTIONS"
    assert "local" in result["detail"]


@pytest.mark.parametrize(
    "model,missing",
    [
        ("bernoulli_simple", "no_losses"),
        ("steady_stokes", "negligible_unsteady_inertia"),
    ],
)
def test_model_requirements_cannot_be_replaced_by_arithmetic(model, missing):
    from studium.verification.scientific import MODEL_REQUIREMENTS

    required = MODEL_REQUIREMENTS[model]
    assumptions = [{"id": key, "left": "0", "relation": "eq", "right": "0"} for key in required if key != missing]
    data = contract([{"kind": "model", "model": model}], assumptions=assumptions)
    result = assess(data)["checks"][0]
    assert result["status"] == "UNVERIFIED" and missing in result["detail"]
    data["assumptions"].append({"id": missing, "left": "1", "relation": "eq", "right": "0"})
    assert outcomes(assess(data)) == ["FAILED"]


def test_point_value_and_propulsion_limit_are_different_checks():
    data = contract(
        [
            {"kind": "defined", "expression": "x/x"},
            {"kind": "limit", "expression": "x/x", "variable": "x", "point": "0", "claimed": "1"},
        ],
        bindings={"x": "0"},
    )
    assert outcomes(assess(data)) == ["FAILED", "SYMBOLICALLY_VERIFIED"]


def test_missing_assumptions_block_even_true_identities():
    data = contract([{"kind": "identity", "left": "x+x", "right": "2*x"}], requires=["steady"])
    assert outcomes(assess(data)) == ["UNVERIFIED"]


def test_dimensions_are_separate_from_symbolic_identity():
    data = contract(
        [
            {"kind": "identity", "left": "x+x", "right": "2*x"},
            {"kind": "dimensions", "expression": "x+x", "expected_unit": "second"},
        ],
        variables={"x": "meter"},
    )
    report = assess(data)
    assert outcomes(report) == ["SYMBOLICALLY_VERIFIED", "FAILED"]
    assert report["verification"]["symbolic"] == "SYMBOLICALLY_VERIFIED"
    assert report["verification"]["dimensions"] == "FAILED"
    assert report["verification"]["numerical_convergence"] == "NOT_CHECKED"


def test_cyclic_bindings_and_untrusted_code_are_rejected():
    data = contract([{"kind": "identity", "left": "x", "right": "y"}], bindings={"x": "y", "y": "x"})
    with pytest.raises(ValueError, match="cycl"):
        assess(data)
    bad = deepcopy(data)
    bad["bindings"] = {}
    bad["representations"][0]["checks"][0]["left"] = "__import__('os').system('true')"
    with pytest.raises(ValueError):
        assess(bad)


def test_euler_constant_is_not_young_modulus_after_binding():
    data = contract([{"kind": "identity", "left": "e", "right": "E"}], variables={"E": "Pa"})
    assert outcomes(assess(data)) == ["FAILED"]


def test_limit_keeps_dependence_hidden_in_definitions():
    data = contract(
        [
            {"kind": "limit", "expression": "y", "variable": "x", "point": "0", "claimed": "1"},
        ],
        bindings={"x": "0", "y": "sin(x)/x"},
    )
    assert outcomes(assess(data)) == ["SYMBOLICALLY_VERIFIED"]


def test_two_sided_limit_does_not_silently_use_right_hand_value():
    data = contract(
        [
            {"kind": "limit", "expression": "abs(x)/x", "variable": "x", "point": "0", "claimed": "1"},
        ]
    )
    assert outcomes(assess(data)) == ["UNVERIFIED"]


def test_pressure_gradient_differentiates_bound_field_not_only_bare_symbols():
    data = contract(
        [{"kind": "gradient", "coordinates": ["x", "y", "z"], "components": ["0", "q", "0"]}],
        variables={"x": "m", "y": "m", "z": "m", "q": "Pa/m"},
        bindings={"q": "x"},
    )
    assert outcomes(assess(data)) == ["FAILED"]


def test_binding_expansion_cannot_bypass_parser_resource_limits():
    data = contract(
        [{"kind": "identity", "left": "z", "right": "1"}], bindings={"x": "2", "y": "x**10000", "z": "y**10000"}
    )
    with pytest.raises(ValueError, match=r"(large|bits|power)"):
        assess(data)


def test_cancelled_self_reference_is_still_a_cycle():
    data = contract([{"kind": "identity", "left": "x", "right": "1"}], bindings={"x": "x/x"})
    with pytest.raises(ValueError, match="cycl"):
        assess(data)


def test_power_divided_by_zero_speed_cannot_describe_startup():
    data = contract(
        [{"kind": "defined", "expression": "P/V"}],
        variables={"P": "watt", "V": "m/s"},
        bindings={"V": "0", "P": "1000"},
    )
    assert outcomes(assess(data)) == ["FAILED"]
    data["bindings"]["V"] = "10"
    assert outcomes(assess(data)) == ["DOMAIN_POINT_CHECKED"]


def test_reynolds_similarity_dimensions_pass_while_viscosity_omission_fails():
    data = contract(
        [
            {"kind": "dimensions", "expression": "U1*(nu2/nu1)*(d1/d2)", "expected_unit": "m/s"},
            {"kind": "identity", "left": "U1*(nu2/nu1)*(d1/d2)", "right": "U1*d1/d2"},
        ],
        variables={"U1": "m/s", "nu1": "m**2/s", "nu2": "m**2/s", "d1": "m", "d2": "m"},
    )
    assert outcomes(assess(data)) == ["DIMENSIONALLY_VERIFIED", "FAILED"]


def test_predicate_success_unknown_and_false_are_distinct():
    from studium.verification.scientific import MODEL_REQUIREMENTS

    data = contract(
        [{"kind": "model", "model": "steady_stokes"}],
        bindings={"x": "1/1000", "y": "0"},
        assumptions=[
            {"id": "small_reynolds", "left": "x", "relation": "lt", "right": "1/100"},
            {"id": "negligible_unsteady_inertia", "left": "y", "relation": "eq", "right": "0"},
        ],
    )
    report = assess(data)
    assert set(report["assumptions"]) == set(MODEL_REQUIREMENTS["steady_stokes"])
    assert outcomes(report) == ["MODEL_CONSISTENT_UNDER_ASSUMPTIONS"]
    assert report["verification"]["assumptions"] == "ASSUMPTIONS_CHECKED"
    del data["bindings"]["y"]
    assert outcomes(assess(data)) == ["UNVERIFIED"]
    data["bindings"]["y"] = "1"
    assert outcomes(assess(data)) == ["FAILED"]


def test_named_equations_are_checked_not_accepted_because_they_were_recorded():
    data = contract([{"kind": "identity", "equation": "eq1"}])
    data["equations"] = [{"id": "eq1", "left": "x+x", "right": "3*x"}]
    assert outcomes(assess(data)) == ["FAILED"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda data: data.update(verification="VERIFIED"),
        lambda data: data.update(bindings={"unknown": "1"}),
        lambda data: data.update(variables={"pi": "m"}),
        lambda data: data["representations"][0].update(role="unknown"),
        lambda data: data["representations"][0].update(checks=[{"kind": "mathematica_verified", "code": "2+2"}]),
        lambda data: data["representations"][0].update(checks=[{"kind": "identity", "equation": "missing"}]),
        lambda data: data.update(assumptions=[{"id": "x", "left": "x", "relation": "probably", "right": "0"}]),
    ],
)
def test_invalid_or_fabricated_verification_input_is_rejected(mutate):
    data = contract([{"kind": "identity", "left": "x", "right": "x"}])
    mutate(data)
    with pytest.raises(ValueError):
        assess(data)


def test_simplification_cannot_hide_an_invalid_real_intermediate():
    data = contract([{"kind": "defined", "expression": "sqrt(x)**2"}], bindings={"x": "-1"})
    assert outcomes(assess(data)) == ["FAILED"]
