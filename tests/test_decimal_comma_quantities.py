"""A quantity written with a decimal comma is read whole, not truncated at the comma."""

import pytest

from studium.authoring.contradictions import _quantities


@pytest.mark.parametrize(
    "text, expected",
    [
        (r"con $\nu = 0{,}33$ el módulo", [("nu", "0.33")]),
        (r"gr = 9{,}81 m/s", [("gr", "9.81")]),
        ("el coeficiente nu = 0,33 y Ey = 200", [("nu", "0.33"), ("ey", "200")]),
        ("rho = 1000 kg", [("rho", "1000")]),
        ("xx = 2.5", [("xx", "2.5")]),
        ("kk = 1,000", [("kk", "1")]),
    ],
)
def test_decimal_comma_is_part_of_the_number(text, expected):
    assert _quantities(text) == expected
