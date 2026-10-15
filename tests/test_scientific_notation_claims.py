"""A numeric relation written in scientific notation is read at the precision it is written with."""

import pytest

from studium.authoring.grounding import _arithmetic_verdict


@pytest.mark.parametrize(
    "statement, verdict",
    [
        (r"71{,}7\times 10^{9}/2810 = 2{,}55\times 10^{7}", "numerically_reproduced"),
        (r"2{,}55\times 10^{7} = 71{,}7\times 10^{9}/2810", "numerically_reproduced"),
        (r"181\times 10^{9}/1600 = 1{,}13\times 10^{8}", "numerically_reproduced"),
        (r"71{,}7\times 10^{9}/2810 = 2{,}56\times 10^{7}", "contradicted"),
        (r"71{,}7\times 10^{9}/2810 = 2{,}5516\times 10^{7}", "numerically_reproduced"),
        (r"6.63\times 10^{-8}/1.0\times 10^{-5} = 6.63\times 10^{-3}", "numerically_reproduced"),
        ("100/8 = 12{,}5", "numerically_reproduced"),
        ("100/8 = 12{,}6", "contradicted"),
    ],
)
def test_scientific_notation_is_a_rounded_value_not_an_exact_quotient(statement, verdict):
    assert _arithmetic_verdict(statement) == verdict
