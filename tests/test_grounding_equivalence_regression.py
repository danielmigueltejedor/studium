"""Regression tests for mathematical relation equivalence."""

import pytest

from studium.authoring.grounding import equivalent_math


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ("x = y", "y = x", True),
        ("F = m*a", "m*a = F", True),
        ("F = m*a", "a = F/m", True),
        ("p = rho*g*h", "p = 2*rho*g*h", False),
        ("V_1 = 2", "V_2 = 2", False),
        ("x = y", "x = y + 1", False),
        ("x = 0", "x*x = 0", False),
        ("F = m*a", "F = 2*m*a", False),
    ],
)
def test_equivalent_math_regression(left, right, expected):
    assert equivalent_math(left, right) is expected


def test_restricted_relation_parser_rejects_python_execution():
    """External equations must not execute arbitrary Python syntax."""
    from studium.authoring.grounding import _relation

    invalid = [
        "x = __import__('os')",
        "x = (lambda y: y)(2)",
        "x = object.attribute",
        "x = a[0]",
        "x = 2**1000000",
    ]

    for equation in invalid:
        assert _relation(equation) is None
