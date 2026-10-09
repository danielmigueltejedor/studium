"""High-level mathematical checks.

Every check returns a :class:`~studium.verification.model.VerificationResult`.
Symbolic calls are wrapped in a wall-clock bound; the input grammar is already
bounded by :mod:`studium.verification.parser`, so the bound is a backstop, not
the only control.

Statuses are never conflated. A symbolic identity becomes
``SYMBOLICALLY_VERIFIED``; two numeric methods agreeing become
``NUMERICALLY_CROSS_CHECKED``; combining two of those becomes
``INDEPENDENTLY_VERIFIED``.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import TypeVar

import sympy

from studium.verification.model import (
    VerificationResult,
    VerificationStatus,
    combine,
)
from studium.verification.parser import ExpressionError, ParsedExpression, parse_expression

DEFAULT_TIMEOUT = 5.0
NUMERIC_DIGITS = 30
TOLERANCE = 1e-9

_T = TypeVar("_T")

_ASSUMPTION_FLAGS = frozenset(
    {"positive", "negative", "real", "integer", "nonzero", "nonnegative", "nonpositive"}
)


class VerificationTimeout(TimeoutError):
    """A symbolic step exceeded the wall-clock bound."""


def _run_bounded(call: Callable[[], _T], timeout: float) -> _T:
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="studium-verify")
    future = executor.submit(call)
    try:
        return future.result(timeout=timeout)
    except FutureTimeout as exc:
        future.cancel()
        raise VerificationTimeout("the check exceeded its time budget") from exc
    finally:
        executor.shutdown(wait=False)


def _unverified(method: str, detail: str, inputs: dict[str, object] | None = None) -> VerificationResult:
    return VerificationResult(
        status=VerificationStatus.UNVERIFIED,
        method=method,
        detail=detail,
        inputs=inputs or {},
    )


def _failed(method: str, detail: str, **kwargs: object) -> VerificationResult:
    return VerificationResult(status=VerificationStatus.FAILED, method=method, detail=detail, **kwargs)  # type: ignore[arg-type]


def _assumed(parsed: ParsedExpression, assumptions: dict[str, tuple[str, ...]] | None) -> sympy.Expr:
    if not assumptions:
        return parsed.expr
    mapping: dict[sympy.Symbol, sympy.Symbol] = {}
    for name, flags in assumptions.items():
        kwargs = {flag: True for flag in flags if flag in _ASSUMPTION_FLAGS}
        mapping[sympy.Symbol(name)] = sympy.Symbol(name, **kwargs)
    return parsed.expr.subs(list(mapping.items()))


def verify_algebraic_equivalence(
    left: str,
    right: str,
    *,
    symbols: set[str] | None = None,
    assumptions: dict[str, tuple[str, ...]] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> VerificationResult:
    """Prove ``left == right`` symbolically, under the stated assumptions."""

    method = "symbolic_equivalence"
    try:
        lhs = parse_expression(left, symbols=symbols)
        rhs = parse_expression(right, symbols=symbols)
    except ExpressionError as exc:
        return _failed(method, str(exc))
    lhs_expr = _assumed(lhs, assumptions)
    rhs_expr = _assumed(rhs, assumptions)
    difference = lhs_expr - rhs_expr
    try:
        simplified = _run_bounded(lambda: sympy.simplify(difference), timeout)
    except VerificationTimeout as exc:
        return _unverified(method, str(exc), {"left": left, "right": right})
    except Exception as exc:
        return _unverified(method, f"simplification did not complete: {exc}", {"left": left, "right": right})
    limitations = (
        "a symbolic identity holds only under the stated assumptions",
        "symbolic validity is not physical validity",
    )
    if simplified == 0:
        return VerificationResult(
            status=VerificationStatus.SYMBOLICALLY_VERIFIED,
            method=method,
            detail="the difference simplifies to zero",
            inputs={"left": left, "right": right, "assumptions": dict(assumptions or {})},
            assumptions=tuple(f"{name}: {','.join(flags)}" for name, flags in (assumptions or {}).items()),
            limitations=limitations,
        )
    decisive = _definitely_nonzero(simplified)
    if decisive is True:
        return _failed(method, f"the difference is not identically zero: {simplified}")
    return _unverified(
        method,
        f"the difference could not be reduced to zero: {simplified}",
        {"left": left, "right": right},
    )


def _definitely_nonzero(expr: sympy.Expr) -> bool | None:
    """Decide whether ``expr`` is a nonzero rational identity.

    Returns ``True`` for a provably nonzero rational expression, ``False`` for
    a provably zero one, and ``None`` when the form (trigonometric,
    transcendental) is outside the decision procedure.
    """

    try:
        cancelled = sympy.cancel(expr)
        numerator, _denominator = sympy.fraction(cancelled)
    except Exception:
        return None
    if numerator.is_number:
        return numerator != 0
    symbols = sorted(numerator.free_symbols, key=str)
    if not symbols:
        return numerator != 0
    try:
        polynomial = sympy.Poly(numerator, *symbols)
    except (sympy.PolynomialError, TypeError, ValueError):
        return None
    return not polynomial.is_zero


def verify_derivative(
    function: str,
    variable: str,
    claimed: str,
    *,
    symbols: set[str] | None = None,
    assumptions: dict[str, tuple[str, ...]] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> VerificationResult:
    """Check that ``claimed`` is the derivative of ``function`` in ``variable``."""

    method = "symbolic_derivative"
    declared = set(symbols or ())
    declared.add(variable)
    try:
        original = parse_expression(function, symbols=declared)
        candidate = parse_expression(claimed, symbols=declared)
    except ExpressionError as exc:
        return _failed(method, str(exc))
    symbol = sympy.Symbol(variable)
    try:
        derivative = _run_bounded(lambda: sympy.diff(original.expr, symbol), timeout)
        difference = derivative - candidate.expr
        simplified = _run_bounded(lambda: sympy.simplify(difference), timeout)
    except VerificationTimeout as exc:
        return _unverified(method, str(exc))
    except Exception as exc:
        return _unverified(method, f"differentiation did not complete: {exc}")
    if simplified == 0:
        return VerificationResult(
            status=VerificationStatus.SYMBOLICALLY_VERIFIED,
            method=method,
            detail=f"d/d{variable} matches the claimed derivative",
            inputs={"function": function, "variable": variable, "claimed": claimed},
            outputs={"derivative": str(derivative)},
            limitations=("the claimed form may still be undefined where the original is not",),
        )
    return _failed(method, f"the claimed derivative differs; computed {derivative}")


def verify_integral(
    function: str,
    variable: str,
    claimed: str,
    *,
    lower: str | None = None,
    upper: str | None = None,
    symbols: set[str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> VerificationResult:
    """Check an antiderivative (indefinite) or a definite integral value."""

    method = "symbolic_integral"
    declared = set(symbols or ())
    declared.add(variable)
    try:
        integrand = parse_expression(function, symbols=declared)
        candidate = parse_expression(claimed, symbols=declared)
    except ExpressionError as exc:
        return _failed(method, str(exc))
    symbol = sympy.Symbol(variable)
    try:
        if lower is None and upper is None:
            difference = sympy.diff(candidate.expr, symbol) - integrand.expr
            simplified = _run_bounded(lambda: sympy.simplify(difference), timeout)
            if simplified == 0:
                return VerificationResult(
                    status=VerificationStatus.SYMBOLICALLY_VERIFIED,
                    method=method,
                    detail="differentiating the claimed antiderivative returns the integrand",
                    inputs={"function": function, "variable": variable, "claimed": claimed},
                    limitations=("antiderivatives differ by a constant; any constant is accepted",),
                )
            return _failed(method, "the claimed antiderivative does not differentiate to the integrand")
        if lower is None or upper is None:
            return _failed(method, "a definite integral needs both limits")
        lower_expr = parse_expression(lower, symbols=declared)
        upper_expr = parse_expression(upper, symbols=declared)
        computed = _run_bounded(
            lambda: sympy.integrate(integrand.expr, (symbol, lower_expr.expr, upper_expr.expr)),
            timeout,
        )
        simplified = _run_bounded(lambda: sympy.simplify(computed - candidate.expr), timeout)
    except VerificationTimeout as exc:
        return _unverified(method, str(exc))
    except Exception as exc:
        return _unverified(method, f"integration did not complete: {exc}")
    if simplified == 0:
        return VerificationResult(
            status=VerificationStatus.SYMBOLICALLY_VERIFIED,
            method=method,
            detail="the definite integral matches the claimed value",
            inputs={"function": function, "variable": variable, "claimed": claimed, "lower": lower, "upper": upper},
            outputs={"integral": str(computed)},
        )
    return _failed(method, f"the definite integral differs; computed {computed}")


def verify_equation(
    left: str,
    right: str,
    *,
    solution: dict[str, str],
    symbols: set[str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> VerificationResult:
    """Substitute a proposed solution and check both sides agree."""

    method = "symbolic_equation"
    declared = set(symbols or ()) | set(solution)
    try:
        lhs = parse_expression(left, symbols=declared)
        rhs = parse_expression(right, symbols=declared)
        substituted = {
            sympy.Symbol(name): parse_expression(value, symbols=declared).expr
            for name, value in solution.items()
        }
    except ExpressionError as exc:
        return _failed(method, str(exc))
    try:
        difference = (lhs.expr - rhs.expr).subs(list(substituted.items()))
        simplified = _run_bounded(lambda: sympy.simplify(difference), timeout)
    except VerificationTimeout as exc:
        return _unverified(method, str(exc))
    except Exception as exc:
        return _unverified(method, f"substitution did not complete: {exc}")
    if simplified == 0:
        return VerificationResult(
            status=VerificationStatus.SYMBOLICALLY_VERIFIED,
            method=method,
            detail="the proposed solution satisfies the equation",
            inputs={"left": left, "right": right, "solution": dict(solution)},
            limitations=("satisfying the equation is not proof the solution is unique",),
        )
    return _failed(method, f"the proposed solution leaves a residual: {simplified}")


def verify_substitution(
    expression: str,
    *,
    values: dict[str, float],
    claimed: float,
    symbols: set[str] | None = None,
    tolerance: float = TOLERANCE,
    timeout: float = DEFAULT_TIMEOUT,
) -> VerificationResult:
    """Evaluate ``expression`` at ``values`` and compare with ``claimed``.

    This reproduces a number. It does not prove the formula.
    """

    method = "numeric_substitution"
    declared = set(symbols or ()) | set(values)
    try:
        parsed = parse_expression(expression, symbols=declared)
        assignment = {
            sympy.Symbol(name): sympy.Rational(str(value))
            for name, value in values.items()
        }
    except ExpressionError as exc:
        return _failed(method, str(exc))
    try:
        replaced = parsed.expr.subs(list(assignment.items()))
        computed = _run_bounded(lambda: sympy.N(replaced, NUMERIC_DIGITS), timeout)
        number = float(computed)
    except VerificationTimeout as exc:
        return _unverified(method, str(exc))
    except Exception as exc:
        return _unverified(method, f"substitution did not complete: {exc}")
    if _close(number, claimed, tolerance):
        return VerificationResult(
            status=VerificationStatus.COMPUTATION_REPRODUCED,
            method=method,
            detail=f"evaluating at the given values gives {number:g}",
            inputs={"expression": expression, "values": dict(values), "claimed": claimed},
            outputs={"computed": number},
            limitations=("a reproduced number is not an independent verification",),
        )
    return _failed(method, f"computed {number:g}, claimed {claimed:g}")


def verify_boundary_condition(
    expression: str,
    *,
    variable: str,
    at: float,
    claimed: float,
    **kwargs: object,
) -> VerificationResult:
    """A boundary or initial condition is a substitution at one point."""

    return verify_substitution(
        expression,
        values={variable: at},
        claimed=claimed,
        symbols={variable},
        **kwargs,  # type: ignore[arg-type]
    )


def verify_limit(
    expression: str,
    *,
    variable: str,
    point: str,
    claimed: str,
    symbols: set[str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> VerificationResult:
    """Check a limit, including one-sided points such as ``0+``."""

    method = "symbolic_limit"
    declared = set(symbols or ())
    declared.add(variable)
    try:
        parsed = parse_expression(expression, symbols=declared)
        target, direction = _limit_point(point, declared)
        expected = parse_expression(claimed, symbols=declared).expr
    except ExpressionError as exc:
        return _failed(method, str(exc))
    symbol = sympy.Symbol(variable)
    try:
        computed = _run_bounded(lambda: sympy.limit(parsed.expr, symbol, target, dir=direction), timeout)
        simplified = _run_bounded(lambda: sympy.simplify(computed - expected), timeout)
    except VerificationTimeout as exc:
        return _unverified(method, str(exc))
    except Exception as exc:
        return _unverified(method, f"limit did not complete: {exc}")
    if simplified == 0:
        return VerificationResult(
            status=VerificationStatus.SYMBOLICALLY_VERIFIED,
            method=method,
            detail=f"the limit is {computed}",
            inputs={"expression": expression, "variable": variable, "point": point, "claimed": claimed},
            outputs={"limit": str(computed)},
        )
    return _failed(method, f"the limit is {computed}, not {claimed}")


def _limit_point(point: str, declared: set[str]) -> tuple[sympy.Expr, str]:
    text = point.strip()
    direction = "+"
    if text.endswith("+"):
        text, direction = text[:-1], "+"
    elif text.endswith("-"):
        text, direction = text[:-1], "-"
    return parse_expression(text.strip(), symbols=declared).expr, direction


def verify_dimensions(
    expression: str,
    symbol_units: dict[str, str],
    *,
    expected_unit: str | None = None,
) -> VerificationResult:
    """Delegate to the Pint-backed dimensional checker."""

    from studium.verification.dimensional import dimension_result

    return dimension_result(expression, symbol_units, expected_unit=expected_unit)


def verify_numeric_cross_check(
    left: str,
    right: str | None = None,
    *,
    symbols: set[str] | None = None,
    samples: list[dict[str, float]] | None = None,
    tolerance: float = TOLERANCE,
    timeout: float = DEFAULT_TIMEOUT,
) -> VerificationResult:
    """Agree between two numeric methods, or between two expressions.

    Two independent methods are used for the same expression: SymPy's ``evalf``
    and an ``mpmath`` lambdify. If two different expressions are given, both
    methods are applied to each and the pairs must agree.
    """

    method = "numeric_cross_check"
    points = samples or _default_samples(symbols or set())
    if not points:
        return _unverified(method, "no sample points were available")
    try:
        parsed_left = parse_expression(left, symbols=symbols)
        parsed_right = parse_expression(right, symbols=symbols) if right is not None else None
    except ExpressionError as exc:
        return _failed(method, str(exc))
    try:
        for point in points:
            assignment = {sympy.Symbol(name): sympy.Rational(str(value)) for name, value in point.items()}
            left_a = _evalf(parsed_left.expr.subs(list(assignment.items())))
            left_b = _lambdify(parsed_left.expr, sorted(parsed_left.symbols), point)
            if not _close(left_a, left_b, tolerance):
                return _failed(method, "the two numeric methods disagreed on the left expression")
            if parsed_right is not None:
                right_a = _evalf(parsed_right.expr.subs(list(assignment.items())))
                right_b = _lambdify(parsed_right.expr, sorted(parsed_right.symbols), point)
                if not _close(right_a, right_b, tolerance):
                    return _failed(method, "the two numeric methods disagreed on the right expression")
                if not _close(left_a, right_a, tolerance):
                    return _failed(
                        method,
                        f"the expressions disagree at {point}: {left_a:g} vs {right_a:g}",
                    )
    except VerificationTimeout as exc:
        return _unverified(method, str(exc))
    except Exception as exc:
        return _unverified(method, f"the numeric cross-check did not complete: {exc}")
    detail = (
        "two numeric methods agree on every sample"
        if parsed_right is None
        else "the two expressions agree on every sample under two numeric methods"
    )
    return VerificationResult(
        status=VerificationStatus.NUMERICALLY_CROSS_CHECKED,
        method=method,
        detail=detail,
        inputs={"left": left, "right": right, "samples": points},
        limitations=("agreement on samples is not a proof for all inputs",),
    )


def verify_combined(results: list[VerificationResult]) -> VerificationResult:
    """Merge several checks over one claim into a single status."""

    return combine(results)


def _evalf(expr: sympy.Expr) -> float:
    if not expr.free_symbols:
        return float(_run_bounded(lambda: sympy.N(expr, NUMERIC_DIGITS), DEFAULT_TIMEOUT))
    raise ExpressionError("a numeric method needs closed-form values")


def _lambdify(expr: sympy.Expr, names: list[str], point: dict[str, float]) -> float:
    function = sympy.lambdify([sympy.Symbol(name) for name in names], expr, modules="mpmath")
    args = [point.get(name, 0.0) for name in names]
    return float(function(*args))


def _default_samples(symbols: set[str]) -> list[dict[str, float]]:
    names = sorted(symbols)
    if not names:
        return []
    base = [0.5, 1.25, 2.0, 3.5]
    return [dict.fromkeys(names, value) for value in base]


def _close(left: float, right: float, tolerance: float) -> bool:
    scale = max(abs(left), abs(right), 1.0)
    return abs(left - right) <= tolerance * scale
