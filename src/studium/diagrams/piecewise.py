"""Piecewise functions of one coordinate, exact where the data are exact.

Numbers given as text or floats become exact rationals (``"2.75"`` is 11/4),
so equilibrium and jump checks are exact. A piece is valid on the open
interval ``(start, end)``; the limits at its ends are its one-sided values.
"""

import math
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, cast

import sympy

X = sympy.Symbol("x", real=True)

#: ``sympy.sympify`` with keyword arguments its stubs do not describe.
sympify_text = cast(Any, sympy.sympify)

_MAX_TEXT = 200


class DataError(ValueError):
    """The structured data cannot be read. The message says which field."""


def exact(value: object, name: str = "value", symbols: dict[str, sympy.Symbol] | None = None) -> sympy.Expr:
    """An exact SymPy number (or a declared parameter expression).

    Floats are read through their shortest decimal text so ``0.1`` is 1/10.
    Text may name declared parameters (``"q*L"``) when ``symbols`` lists them.
    """

    if isinstance(value, bool) or value is None:
        raise DataError(f"{name} must be a number")
    if isinstance(value, int):
        return sympy.Integer(value)
    if isinstance(value, Fraction):
        return sympy.Rational(value.numerator, value.denominator)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise DataError(f"{name} must be finite")
        return sympy.Rational(repr(value))
    if isinstance(value, str):
        text = value.strip().replace(",", ".") if _plain_decimal(value) else value.strip()
        if not text or len(text) > _MAX_TEXT:
            raise DataError(f"{name} must be a number")
        if _plain_decimal(text):
            return sympy.Rational(text)
        allowed = dict(symbols or {})
        try:
            parsed = sympify_text(text, locals=allowed, rational=True)
        except (sympy.SympifyError, SyntaxError, TypeError, ValueError) as exc:
            raise DataError(f"{name} is not a number or a declared parameter expression") from exc
        unknown = {str(item) for item in parsed.free_symbols} - set(allowed)
        if unknown:
            raise DataError(f"{name} uses undeclared parameters: {', '.join(sorted(unknown))}")
        return parsed
    raise DataError(f"{name} must be a number")


def _plain_decimal(text: str) -> bool:
    body = text.strip()
    if body.startswith(("+", "-")):
        body = body[1:]
    if body.count(".") + body.count(",") > 1:
        return False
    digits = body.replace(".", "").replace(",", "")
    if "e" in digits.lower():
        mantissa, _, exponent = digits.lower().partition("e")
        exponent = exponent.lstrip("+-")
        return mantissa.isdigit() and exponent.isdigit()
    return digits.isdigit()


@dataclass(frozen=True)
class Piece:
    start: sympy.Expr
    end: sympy.Expr
    expr: sympy.Expr

    def at(self, value: sympy.Expr) -> sympy.Expr:
        return sympy.simplify(self.expr.subs(X, value))


@dataclass(frozen=True)
class Piecewise:
    """Ordered, contiguous pieces of one function of ``x``."""

    name: str
    pieces: tuple[Piece, ...]

    def __post_init__(self) -> None:
        for left, right in zip(self.pieces, self.pieces[1:], strict=False):
            if sympy.simplify(left.end - right.start) != 0:
                raise DataError(f"{self.name}: pieces are not contiguous")

    @property
    def start(self) -> sympy.Expr:
        return self.pieces[0].start

    @property
    def end(self) -> sympy.Expr:
        return self.pieces[-1].end

    def piece_at(self, value: sympy.Expr) -> Piece:
        for piece in self.pieces:
            if bool(piece.start <= value <= piece.end):
                return piece
        raise DataError(f"{self.name}: {value} is outside the domain")

    def left(self, value: sympy.Expr) -> sympy.Expr:
        """Limit from the left. At the first start it is the first piece's value."""

        for piece in self.pieces:
            if bool(piece.start < value <= piece.end):
                return piece.at(value)
        return self.pieces[0].at(value)

    def right(self, value: sympy.Expr) -> sympy.Expr:
        for piece in self.pieces:
            if bool(piece.start <= value < piece.end):
                return piece.at(value)
        return self.pieces[-1].at(value)

    def jump(self, value: sympy.Expr) -> sympy.Expr:
        return sympy.simplify(self.right(value) - self.left(value))

    def derivative(self, name: str | None = None) -> "Piecewise":
        return Piecewise(
            name or f"d{self.name}/dx",
            tuple(Piece(piece.start, piece.end, sympy.expand(sympy.diff(piece.expr, X))) for piece in self.pieces),
        )

    def is_numeric(self) -> bool:
        return all(not piece.expr.free_symbols - {X} and piece.start.is_number and piece.end.is_number for piece in self.pieces)

    def critical_points(self) -> list[sympy.Expr]:
        """Interior points where the derivative vanishes (real roots only)."""

        found: list[sympy.Expr] = []
        for piece in self.pieces:
            slope = sympy.diff(piece.expr, X)
            if slope.free_symbols - {X} or sympy.simplify(slope) == 0:
                continue
            for root in sympy.solve(sympy.Eq(slope, 0), X):
                if root.is_real and bool(piece.start < root < piece.end):
                    found.append(root)
        return found

    def zeros(self) -> list[sympy.Expr]:
        """Interior points where a piece crosses zero (real roots only)."""

        found: list[sympy.Expr] = []
        for piece in self.pieces:
            if piece.expr.free_symbols - {X} or sympy.simplify(piece.expr) == 0:
                continue
            for root in sympy.solve(sympy.Eq(piece.expr, 0), X):
                if root.is_real and bool(piece.start < root < piece.end):
                    found.append(root)
        return found

    def as_dict(self, decimals: int = 6) -> dict[str, object]:
        return {
            "name": self.name,
            "pieces": [
                {
                    "from": _text(piece.start),
                    "to": _text(piece.end),
                    "expr": str(sympy.expand(piece.expr)),
                    "latex": sympy.latex(_display(piece.expr, decimals)),
                }
                for piece in self.pieces
            ],
        }


def _display(expr: sympy.Expr, decimals: int) -> sympy.Expr:
    """Integers stay exact; other rational coefficients print as rounded decimals."""

    expanded = sympy.expand(expr)
    if expanded.free_symbols - {X} or not expanded.is_polynomial(X):
        return expanded
    terms = []
    for (power,), coefficient in sympy.Poly(expanded, X).terms():
        value = coefficient
        if not (value.is_Rational and value.q == 1):
            value = sympy.Float(round(float(value), decimals), 15)
        terms.append(value * X**power)
    return sympy.Add(*terms)


def _text(value: sympy.Expr) -> str:
    return str(value)


def as_float(value: object) -> float:
    return float(sympy.N(sympy.sympify(value), 30))


def format_number(value: object, *, decimals: int = 2, comma: bool = False) -> str:
    """Rounded text, trailing zeros dropped, optional decimal comma, true minus sign."""

    number = as_float(value)
    if number != 0 and abs(number) < 10 ** (1 - decimals):
        # Small values keep three significant digits instead of rounding to zero.
        decimals = min(12, 2 - math.floor(math.log10(abs(number))))
    text = f"{number:.{decimals}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in ("-0", ""):
        text = "0"
    if comma:
        text = text.replace(".", "{,}")
    return text
