"""Comparing an author's stated value with an exact result.

A decimal claim agrees when the exact value lies within half a unit of its
last written digit (``"58.6"`` accepts 58.55 to 58.65). An integer, a fraction
or an expression must be exactly equal.
"""

import sympy

from studium.diagrams.piecewise import DataError, as_float, exact


def compare(name: str, claimed_value: object, actual: sympy.Expr, parameters) -> tuple[str, str, bool, str, object]:
    try:
        claimed = exact(claimed_value, name, parameters)
    except DataError as exc:
        return name, "symbolic", False, str(exc), None
    decimals = decimals_of(claimed_value)
    if decimals is None or not actual.is_number:
        difference = sympy.simplify(claimed - actual)
        return name, "symbolic", difference == 0, f"claimed {claimed}, computed {actual}", difference
    # A decimal claim agrees when the exact value lies within half a unit of its last written digit.
    agree = abs(as_float(claimed) - as_float(actual)) <= 0.5 * 10 ** (-decimals) * (1 + 1e-9)
    return name, "numeric", agree, f"claimed {claimed_value}, computed {as_float(actual):.6g}", as_float(claimed) - as_float(actual)


def decimals_of(value: object) -> int | None:
    """Decimals written in a decimal claim, or None for an exact claim (integer, fraction, expression)."""

    if isinstance(value, float):
        text = repr(value)
    elif isinstance(value, str):
        text = value.strip().replace(",", ".")
    else:
        return None
    if "/" in text or not any(character.isdigit() for character in text):
        return None
    if "." not in text or "e" in text.lower():
        return None
    return len(text.split(".", 1)[1])
