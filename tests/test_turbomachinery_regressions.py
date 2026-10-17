"""Small synthetic regressions from the turbomachinery authoring workflow."""

import pytest

from studium.authoring.mathematics import MathError, substitution_latex, unit_latex
from studium.authoring.render import _body_record_lines, _heading_from_paragraph
from studium.verification.dimensional import check_dimensions
from studium.verification.engine import verify_dimensions
from studium.verification.model import VerificationStatus


@pytest.mark.parametrize(
    "unit,expected",
    [
        ("1/s", r"\mathrm{s}^{-1}"),
        ("kg m⁻³ s⁻¹", r"\mathrm{kg}\,\mathrm{m}^{-3}\,\mathrm{s}^{-1}"),
        ("1/(kg*s)", r"\mathrm{kg}^{-1}\,\mathrm{s}^{-1}"),
        ("K^0.5", r"\mathrm{K}^{\frac{1}{2}}"),
        ("K**(-0.5)", r"\mathrm{K}^{\frac{-1}{2}}"),
        ("m^(1/3)", r"\mathrm{m}^{\frac{1}{3}}"),
        ("(m/s)^2", r"\mathrm{m}^{2}\,\mathrm{s}^{-2}"),
        ("kg*m/(s^2*K^0.5)", r"\mathrm{kg}\,\mathrm{m}\,\mathrm{s}^{-2}\,\mathrm{K}^{\frac{-1}{2}}"),
        ("m/m", "1"),
        ("m^0", "1"),
        ("kg/m*s", r"\mathrm{kg}\,\mathrm{m}^{-1}\,\mathrm{s}"),
    ],
)
def test_units_preserve_reciprocals_roots_and_product_dimensions(unit, expected):
    assert unit_latex(unit) == expected


@pytest.mark.parametrize("unit", ["(m/s", "m/s)", "m/", "m*", "m^^2", "K^(1/0)", "K^(x)", "2/s", "m^nan", r"m\input{x}"])
def test_malformed_units_are_not_silently_printed(unit):
    with pytest.raises(MathError):
        unit_latex(unit)


def test_fractional_unit_survives_a_structured_substitution():
    tex = substitution_latex("capacity*sqrt(temperature)", {"capacity": ("2", "kg/(s*K^0.5)"), "temperature": ("300", "K")})
    assert r"\mathrm{K}^{\frac{-1}{2}}" in tex
    assert "300" in tex


def test_polytropic_pressure_ratio_has_dimensionless_variable_exponent():
    units = {"Tin": "K", "pout": "Pa", "pin": "Pa", "gamma": "dimensionless", "eta_p": "dimensionless"}
    check = check_dimensions("Tin*(pout/pin)**((gamma-1)/(gamma*eta_p))", units, expected_unit="K")
    assert check.consistent
    result = verify_dimensions("(pout/pin)**((gamma-1)/gamma)", units, expected_unit="dimensionless")
    assert result.status is VerificationStatus.DIMENSIONALLY_VERIFIED
    assert "physically" in " ".join(result.limitations)


@pytest.mark.parametrize(
    "expression,units",
    [
        ("ratio**gamma", {"ratio": "dimensionless", "gamma": "K"}),
        ("length**gamma", {"length": "m", "gamma": "dimensionless"}),
        ("ratio**missing", {"ratio": "dimensionless"}),
        ("ratio**(gamma+T)", {"ratio": "dimensionless", "gamma": "dimensionless", "T": "K"}),
    ],
)
def test_power_support_does_not_accept_dimensionful_or_unknown_exponents(expression, units):
    result = verify_dimensions(expression, units, expected_unit="dimensionless")
    assert not result.ok
    assert result.status is VerificationStatus.FAILED


@pytest.mark.parametrize(
    "lead",
    ["Así,", "Aplicando el balance:", r"Para \(C_x\) constante,", "Con $U$ dado:", "Si Cx = 180:", r"\[p=\rho R T\]"],
)
def test_prose_leading_into_an_equation_does_not_become_a_heading(lead):
    text = lead + "\n" + r"\[w=U(C_{\theta2}-C_{\theta1})\]"
    assert _heading_from_paragraph(text) == (None, text)
    rendered = "\n".join(_body_record_lines(text, ""))
    assert r"\section{" not in rendered
    assert r"\[" in rendered


def test_short_existing_titles_and_generic_leads_keep_their_contract():
    assert _heading_from_paragraph("Cinemática\nEl movimiento tiene su propio apartado.") == ("Cinemática", "El movimiento tiene su propio apartado.")
    assert _heading_from_paragraph("Explicación\nTexto del cuerpo.") == (None, "Texto del cuerpo.")


@pytest.mark.parametrize("code,level,kind", [("es", "Nivel de examen", "Identificación de errores"), ("en", "Exam level", "Error identification"), ("nl", "Exam level", "Error identification")])
def test_problem_tags_use_readable_labels_without_changing_enum_values(code, level, kind):
    from studium.authoring.problems import EXERCISE_DIFFICULTIES, PROBLEM_TYPES
    from studium.authoring.render import _problem_tag
    from studium.domain.languages import describe

    language = describe(code)
    assert language is not None
    assert _problem_tag("EXAM_LEVEL", language) == level
    assert _problem_tag("ERROR_IDENTIFICATION", language) == kind
    assert _problem_tag("FUTURE_LEVEL", language) == "FUTURE_LEVEL"
    assert "EXAM_LEVEL" in EXERCISE_DIFFICULTIES
    assert "ERROR_IDENTIFICATION" in PROBLEM_TYPES


@pytest.mark.parametrize("unit", ["11/s", "1.5/s", "m1", "(" * 26 + "m" + ")" * 26, "m" * 201])
def test_unit_parser_is_bounded_and_does_not_drop_numeric_scales(unit):
    with pytest.raises(MathError):
        unit_latex(unit)


@pytest.mark.parametrize("expression", ["ratio**(1/0)", "ratio**(1/(1-1))", "ratio**(gamma/(1-1))", "ratio**1e1000"])
def test_invalid_literal_exponents_do_not_pass_the_dimensionless_shortcut(expression):
    result = verify_dimensions(expression, {"ratio": "dimensionless", "gamma": "dimensionless"}, expected_unit="dimensionless")
    assert not result.ok
    assert result.status is VerificationStatus.FAILED


def test_literal_arithmetic_exponent_keeps_dimensions_exact():
    assert check_dimensions("length**(1+1/2)", {"length": "m"}, expected_unit="m**1.5").consistent
