"""Dimensional consistency via Pint.

Unit *strings* are parsed by Pint into a base-dimension exponent vector. A
formula is then walked over those vectors with the same allowlisted grammar as
:mod:`studium.verification.parser`. We never ask Pint to evaluate an arbitrary
expression string, only to parse a bounded unit token such as ``kg*m/s**2``.

A dimensionally consistent equation can still be physically wrong. This module
only answers the dimensional question.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from fractions import Fraction

import pint

from studium.verification.model import VerificationResult, VerificationStatus

MAX_UNIT_LENGTH = 200
_UNIT_OK = re.compile(r"^[A-Za-z0-9 _*/.()^\-]+$")

REGISTRY = pint.UnitRegistry()

BaseDims = dict[str, Fraction]

_ADDITIVE = (ast.Add, ast.Sub)
_MULT = (ast.Mult,)
_DIV = (ast.Div,)

#: Functions whose argument must be dimensionless and whose result is dimensionless.
_TRANSCENDENTAL = frozenset(
    {
        "sin",
        "cos",
        "tan",
        "cot",
        "sec",
        "csc",
        "asin",
        "acos",
        "atan",
        "sinh",
        "cosh",
        "tanh",
        "asinh",
        "acosh",
        "atanh",
        "exp",
        "log",
        "ln",
        "floor",
        "ceiling",
    }
)
_ROOT = {"sqrt": Fraction(1, 2), "cbrt": Fraction(1, 3)}
_PASSTHROUGH = frozenset({"abs", "Abs", "Min", "Max"})


class DimensionError(ValueError):
    """The unit string or formula is outside the dimensional grammar."""


@dataclass(frozen=True)
class DimensionCheck:
    dims: BaseDims
    expected: BaseDims | None
    consistent: bool
    detail: str


def _zero() -> BaseDims:
    return {}


def _add(left: BaseDims, right: BaseDims, factor: int = 1) -> BaseDims:
    result = dict(left)
    for key, value in right.items():
        combined = result.get(key, Fraction(0)) + factor * value
        if combined == 0:
            result.pop(key, None)
        else:
            result[key] = combined
    return result


def _scale(dims: BaseDims, factor: Fraction) -> BaseDims:
    result: BaseDims = {}
    for key, value in dims.items():
        scaled = value * factor
        if scaled != 0:
            result[key] = scaled
    return result


def parse_units(text: object) -> BaseDims:
    """Parse a bounded unit token into base dimensions. ``kg*m/s**2`` is fine."""

    if not isinstance(text, str):
        raise DimensionError("unit must be a string")
    cleaned = text.strip()
    if not cleaned:
        raise DimensionError("unit is empty")
    if len(cleaned) > MAX_UNIT_LENGTH:
        raise DimensionError("unit is too long")
    if not _UNIT_OK.fullmatch(cleaned):
        raise DimensionError("unit contains a rejected character")
    try:
        unit = REGISTRY.parse_units(cleaned)
        dimensionality = unit.dimensionality
    except (pint.errors.PintError, ValueError, TypeError, KeyError) as exc:
        raise DimensionError(f"unit is not recognised: {cleaned!r}") from exc
    dims: BaseDims = {}
    for key, value in dimensionality.items():
        name = str(key)
        exponent = Fraction(str(value)) if not isinstance(value, Fraction) else value
        if exponent != 0:
            dims[name] = exponent
    return dims


def convert(value: float, from_unit: str, to_unit: str) -> float:
    """Convert a magnitude between two compatible units."""

    parse_units(from_unit)
    parse_units(to_unit)
    try:
        quantity = REGISTRY.Quantity(value, from_unit)
        return float(quantity.to(to_unit).magnitude)
    except (pint.errors.PintError, ValueError, TypeError, KeyError) as exc:
        raise DimensionError(f"cannot convert {from_unit!r} to {to_unit!r}") from exc


def _format(dims: BaseDims) -> str:
    if not dims:
        return "dimensionless"
    parts = []
    for key in sorted(dims):
        exponent = dims[key]
        number = exponent.numerator if exponent.denominator == 1 else f"({exponent.numerator}/{exponent.denominator})"
        parts.append(f"{key}^{number}")
    return "*".join(parts)


def check_dimensions(
    expression: str,
    symbol_units: dict[str, str],
    *,
    expected_unit: str | None = None,
) -> DimensionCheck:
    """Walk ``expression`` over the dimensions of ``symbol_units``.

    Addition of two different dimensions is inconsistent. A transcendental
    function needs a dimensionless argument. ``sqrt`` halves the exponents.
    """

    declared: dict[str, BaseDims] = {}
    for name, unit in symbol_units.items():
        if not isinstance(name, str) or not name.isidentifier() or name.startswith("_"):
            raise DimensionError(f"bad symbol name: {name!r}")
        declared[name] = parse_units(unit)
    expected = parse_units(expected_unit) if expected_unit is not None else None

    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except (SyntaxError, ValueError) as exc:
        raise DimensionError("formula is not valid syntax") from exc
    if not isinstance(tree, ast.Expression):
        raise DimensionError("formula is not valid syntax")

    dims = _walk(tree.body, declared, depth=0)
    consistent = expected is None or dims == expected
    if expected is None:
        detail = f"formula reduces to {_format(dims)}"
    elif consistent:
        detail = f"formula reduces to {_format(dims)}, matching {expected_unit}"
    else:
        detail = f"formula reduces to {_format(dims)}, expected {_format(expected)}"
    return DimensionCheck(dims=dims, expected=expected, consistent=consistent, detail=detail)


def _walk(node: ast.AST, declared: dict[str, BaseDims], *, depth: int) -> BaseDims:
    if depth > 24:
        raise DimensionError("formula nests too deeply")

    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise DimensionError("only numeric constants are allowed")
        return _zero()

    if isinstance(node, ast.Name):
        if node.id not in declared:
            raise DimensionError(f"no dimension given for {node.id!r}")
        return dict(declared[node.id])

    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        return _walk(node.operand, declared, depth=depth + 1)

    if isinstance(node, ast.BinOp):
        left = _walk(node.left, declared, depth=depth + 1)
        right = _walk(node.right, declared, depth=depth + 1)
        if isinstance(node.op, _ADDITIVE):
            if left != right:
                raise DimensionError(
                    f"cannot add {_format(left)} to {_format(right)}"
                )
            return left
        if isinstance(node.op, _MULT):
            return _add(left, right, 1)
        if isinstance(node.op, _DIV):
            return _add(left, right, -1)
        if isinstance(node.op, ast.Pow):
            exponent = _exponent(node.right, declared)
            if exponent is None:
                raise DimensionError("exponent must be a numeric constant")
            return _scale(left, exponent)
        raise DimensionError("operator is not allowed in a dimension check")

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.keywords:
            raise DimensionError("only allowlisted functions are allowed")
        name = node.func.id
        args = [_walk(arg, declared, depth=depth + 1) for arg in node.args]
        if name in _ROOT and len(args) == 1:
            return _scale(args[0], _ROOT[name])
        if name in _TRANSCENDENTAL and len(args) == 1:
            if args[0] != _zero():
                raise DimensionError(f"{name} needs a dimensionless argument")
            return _zero()
        if name in _PASSTHROUGH and args:
            first = args[0]
            if any(arg != first for arg in args):
                raise DimensionError(f"{name} arguments disagree in dimension")
            return first
        if name == "sign" and len(args) == 1:
            return _zero()
        if name == "atan2" and len(args) == 2:
            if args[0] != args[1]:
                raise DimensionError("atan2 arguments disagree in dimension")
            return _zero()
        raise DimensionError(f"function is not allowed in a dimension check: {name!r}")

    raise DimensionError(f"formula element is not allowed: {type(node).__name__}")


def _exponent(node: ast.AST, declared: dict[str, BaseDims]) -> Fraction | None:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            return None
        return Fraction(str(node.value))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        inner = _exponent(node.operand, declared)
        if inner is None:
            return None
        return inner if isinstance(node.op, ast.UAdd) else -inner
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left = _exponent(node.left, declared)
        right = _exponent(node.right, declared)
        if left is None or right is None or right == 0:
            return None
        return left / right
    return None


def dimension_result(expression: str, symbol_units: dict[str, str], *, expected_unit: str | None = None) -> VerificationResult:
    """Wrap :func:`check_dimensions` in a structured verification result."""

    try:
        check = check_dimensions(expression, symbol_units, expected_unit=expected_unit)
    except DimensionError as exc:
        return VerificationResult(
            status=VerificationStatus.FAILED,
            method="dimensional",
            detail=str(exc),
            inputs={"expression": expression, "symbol_units": dict(symbol_units)},
            limitations=("dimensional consistency is necessary but not sufficient",),
        )
    status = VerificationStatus.DIMENSIONALLY_VERIFIED if check.consistent else VerificationStatus.FAILED
    return VerificationResult(
        status=status,
        method="dimensional",
        detail=check.detail,
        inputs={"expression": expression, "symbol_units": dict(symbol_units), "expected_unit": expected_unit},
        outputs={"dimensionality": {key: str(value) for key, value in check.dims.items()}},
        limitations=("dimensionally consistent does not mean physically correct",),
    )
