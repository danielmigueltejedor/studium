"""E (Young's modulus) and I (second moment of area) are symbols in a book, not Euler's number or the imaginary unit."""

import pytest

from studium.authoring.mathematics import substitution_latex, symbolic_latex
from studium.authoring.render import _symbol_tex


def test_substitution_replaces_young_modulus_instead_of_printing_e():
    tex = substitution_latex("rho*k*L**2/E", {"rho": ("2810", "kg/m^3"), "k": ("5e7", "N/m"), "L": ("2", "m"), "E": ("71.7e9", "Pa")})
    assert "71.7e9" in tex
    assert "e}" not in tex.replace(r"\left", "").replace("e9", "")


def test_second_moment_symbol_is_substituted():
    tex = substitution_latex("P*L**3/(3*E*I)", {"P": ("1000", "N"), "L": ("2", "m"), "E": ("70e9", "Pa"), "I": ("1e-6", "m^4")})
    assert "70e9" in tex and "1e-6" in tex


@pytest.mark.parametrize("name, tex", [("E", "E"), ("I", "I"), ("E_i", "E_{i}"), ("I_z", "I_{z}")])
def test_variable_names_keep_their_letters(name, tex):
    assert _symbol_tex(name) == tex


@pytest.mark.parametrize("name, tex", [("delta_{11}", r"\delta_{11}"), ("delta_10", r"\delta_{10}"), ("lambda_1", r"\lambda_{1}"), ("sigma_x", r"\sigma_{x}")])
def test_greek_words_with_subscripts_are_typeset(name, tex):
    assert _symbol_tex(name) == tex


def test_euler_number_is_lowercase_e_and_capital_e_is_a_symbol():
    assert symbolic_latex("e**2") == "e^{2}"
    assert symbolic_latex("E**2") == "E^{2}"
