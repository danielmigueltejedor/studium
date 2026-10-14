"""Scientific checks for structured academic problems.

A dimensional check cannot establish mathematical or physical validity.
"""

import math
from collections.abc import Mapping
from fractions import Fraction

import pint
import sympy

from studium.authoring.computation import precision_verdict
from studium.verification.dimensional import REGISTRY, DimensionError, check_dimensions
from studium.verification.model import VerificationResult, VerificationStatus
from studium.verification.parser import ExpressionError, parse_expression

_METHOD = "problem_dimensional_consistency"
_LIMITATIONS = (
    "Dimensional consistency does not prove physical validity.",
    "This check does not verify numerical results or physical assumptions.",
)


def _unverified(detail: str) -> VerificationResult:
    return VerificationResult(
        status=VerificationStatus.UNVERIFIED,
        method=_METHOD,
        detail=detail,
        limitations=_LIMITATIONS,
    )


def verify_problem_dimensions(
    solution: Mapping[str, object],
    *,
    expected_unit: str | None = None,
) -> VerificationResult:
    """Check the dimensions of one structured symbolic model.

    Only a single symbolic model is supported in this initial version.
    The expected output unit must be supplied explicitly.

    No stored content is modified.
    """

    models = solution.get("model")

    if not isinstance(models, list) or len(models) != 1:
        return _unverified(
            "Exactly one symbolic model is required for this check."
        )

    model = models[0]

    if not isinstance(model, dict):
        return _unverified("The model is not a structured equation.")

    expression = model.get("symbolic")

    if not isinstance(expression, str) or not expression.strip():
        return _unverified("The model has no symbolic expression.")

    given = solution.get("given")

    if not isinstance(given, list) or not given:
        return _unverified("Numerical data and their units are missing.")

    symbol_units: dict[str, str] = {}

    for entry in given:
        if not isinstance(entry, dict):
            return _unverified("A given quantity is not structured.")

        symbol = entry.get("symbol")
        unit = entry.get("unit")

        if not isinstance(symbol, str) or not symbol.isidentifier():
            return _unverified("A given quantity has an invalid symbol.")

        if not isinstance(unit, str) or not unit.strip():
            return _unverified(f"Unit missing for {symbol!r}.")

        if symbol in symbol_units:
            return _unverified(f"Duplicate given symbol: {symbol!r}.")

        symbol_units[symbol] = unit

    try:
        check = check_dimensions(
            expression,
            symbol_units,
            expected_unit=expected_unit,
        )
    except DimensionError as exc:
        detail = str(exc)

        # An incompatible addition is a demonstrated dimensional error.
        # Missing symbols, unsupported expressions and invalid unit tokens
        # are inconclusive, not evidence of a false physical equation.
        status = (
            VerificationStatus.FAILED
            if detail.startswith("cannot add ")
            else VerificationStatus.UNVERIFIED
        )

        return VerificationResult(
            status=status,
            method=_METHOD,
            detail=detail,
            inputs={
                "expression": expression,
                "symbol_units": symbol_units,
                "expected_unit": expected_unit,
            },
            limitations=_LIMITATIONS,
        )

    dimensions = {
        name: str(exponent)
        for name, exponent in check.dims.items()
    }

    if not check.consistent:
        status = VerificationStatus.FAILED
    elif expected_unit is None:
        status = VerificationStatus.UNVERIFIED
    else:
        status = VerificationStatus.DIMENSIONALLY_VERIFIED

    return VerificationResult(
        status=status,
        method=_METHOD,
        detail=check.detail,
        inputs={
            "expression": expression,
            "symbol_units": symbol_units,
            "expected_unit": expected_unit,
        },
        outputs={"dimensions": dimensions},
        limitations=_LIMITATIONS,
    )


def verify_problem_numeric(
    solution: Mapping[str, object],
    *,
    expected_value: float,
    expected_unit: str,
    expected_text: str | None = None,
) -> VerificationResult:
    """Reproduce one model calculation using quantities in base units.

    A matching value proves only that this calculation was reproduced.
    It does not establish the correctness of the physical model, its
    assumptions, or the origin of the expected result.
    """
    method = "problem_numeric_reproduction"
    limitations = (
        "The expected result is supplied by the caller, not independently established.",
        "A reproduced calculation does not prove physical validity.",
        "The model is interpreted using coherent base units.",
    )

    def unverified(detail: str) -> VerificationResult:
        return VerificationResult(
            status=VerificationStatus.UNVERIFIED,
            method=method,
            detail=detail,
            limitations=limitations,
        )

    if (
        isinstance(expected_value, bool)
        or not isinstance(expected_value, (int, float))
        or not math.isfinite(float(expected_value))
    ):
        return unverified("The expected value must be a finite number.")

    dimension_result = verify_problem_dimensions(
        solution,
        expected_unit=expected_unit,
    )

    if dimension_result.status is VerificationStatus.FAILED:
        return VerificationResult(
            status=VerificationStatus.FAILED,
            method=method,
            detail="Dimensional inconsistency: " + dimension_result.detail,
            limitations=limitations,
        )

    if dimension_result.status is not VerificationStatus.DIMENSIONALLY_VERIFIED:
        return unverified(
            "Dimensional verification is incomplete: "
            + dimension_result.detail
        )

    models = solution.get("model")
    given = solution.get("given")

    if (
        not isinstance(models, list)
        or len(models) != 1
        or not isinstance(models[0], dict)
        or not isinstance(given, list)
        or len(given) > 32
    ):
        return unverified("The model or input data are unsupported.")

    symbolic = models[0].get("symbolic")

    if not isinstance(symbolic, str):
        return unverified("No symbolic model is available.")

    quantities: dict[str, float] = {}

    try:
        for entry in given:
            if not isinstance(entry, dict):
                return unverified("Invalid given quantity.")

            symbol = entry.get("symbol")
            unit = entry.get("unit")
            raw_value = entry.get("value")

            if (
                not isinstance(symbol, str)
                or not symbol.isidentifier()
                or not isinstance(unit, str)
                or isinstance(raw_value, bool)
                or not isinstance(raw_value, (str, int, float))
                or len(str(raw_value)) > 40
            ):
                return unverified("Invalid numerical input.")

            magnitude = float(raw_value)

            if not math.isfinite(magnitude):
                return unverified("A numerical input is not finite.")

            quantity = REGISTRY.Quantity(magnitude, unit)
            base_value = float(quantity.to_base_units().magnitude)

            if not math.isfinite(base_value):
                return unverified("A converted input is not finite.")

            if symbol in quantities:
                return unverified(f"Duplicate symbol: {symbol!r}.")

            quantities[symbol] = base_value

        parsed = parse_expression(
            symbolic,
            symbols=set(quantities),
        )

        substitutions = {
            sympy.Symbol(name): sympy.Float(value, 16)
            for name, value in quantities.items()
        }

        calculated_expr = parsed.expr.subs(list(substitutions.items()))
        calculated = float(sympy.N(calculated_expr, 16))

        expected_quantity = REGISTRY.Quantity(
            float(expected_value),
            expected_unit,
        )

        expected_base = float(
            expected_quantity.to_base_units().magnitude
        )

    except (
        ExpressionError,
        pint.errors.PintError,
        ValueError,
        TypeError,
        OverflowError,
        ZeroDivisionError,
    ) as exc:
        return unverified(f"The calculation could not be reproduced: {exc}")

    if not math.isfinite(calculated) or not math.isfinite(expected_base):
        return unverified("The calculation produced a non-finite value.")

    if expected_text is not None:
        # The stated answer is compared at the precision it is written with, in its own unit.
        factor = expected_base / float(expected_value) if float(expected_value) != 0 else None
        if factor is None or not math.isfinite(factor) or factor == 0:
            return unverified("The stated answer cannot be compared in its unit.")
        verdict = precision_verdict(expected_text, Fraction(calculated / factor))
        if verdict == "ambiguous":
            return unverified(
                "The stated answer ends in zeros that may not be significant; the model agrees only if they are placeholders."
            )
        reproduced = verdict == "agrees"
    else:
        reproduced = math.isclose(
            calculated,
            expected_base,
            rel_tol=1e-9,
            abs_tol=1e-12,
        )

    return VerificationResult(
        status=(
            VerificationStatus.COMPUTATION_REPRODUCED
            if reproduced
            else VerificationStatus.FAILED
        ),
        method=method,
        detail=(
            "The numerical result was reproduced."
            if reproduced
            else "The numerical result differs from the expected value."
        ),
        inputs={
            "expression": symbolic,
            "expected_value": expected_value,
            "expected_unit": expected_unit,
        },
        outputs={
            "calculated_base_value": calculated,
            "expected_base_value": expected_base,
        },
        limitations=limitations,
    )
