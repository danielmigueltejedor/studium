"""An allowlisted expression parser.

Untrusted text never reaches ``eval``, ``exec``, ``sympy.sympify`` or
``sympy.parser.parse_expr``. We parse the text with :mod:`ast`, walk a fixed
allowlist of node types, and build SymPy objects ourselves.

Anything outside the allowlist is rejected. The walk enforces size, depth,
symbol, call and integer-bit limits so a small string cannot request a huge
computation.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

import sympy

MAX_EXPRESSION = 1000
MAX_NODES = 200
MAX_DEPTH = 24
MAX_SYMBOLS = 40
MAX_CALLS = 40
MAX_INTEGER_BITS = 256
_MAX_POW_EXPONENT = 10_000
_MAX_POW_BITS = 1_000_000

#: Names that always resolve to a mathematical constant, never a symbol.
CONSTANTS: dict[str, sympy.Expr] = {
    "pi": sympy.pi,
    "E": sympy.E,
    "e": sympy.E,
}

#: Allowlisted functions. Keys are the only callable names.
FUNCTIONS: dict[str, object] = {
    "sin": sympy.sin,
    "cos": sympy.cos,
    "tan": sympy.tan,
    "cot": sympy.cot,
    "sec": sympy.sec,
    "csc": sympy.csc,
    "asin": sympy.asin,
    "acos": sympy.acos,
    "atan": sympy.atan,
    "atan2": sympy.atan2,
    "sinh": sympy.sinh,
    "cosh": sympy.cosh,
    "tanh": sympy.tanh,
    "asinh": sympy.asinh,
    "acosh": sympy.acosh,
    "atanh": sympy.atanh,
    "exp": sympy.exp,
    "log": sympy.log,
    "ln": sympy.log,
    "sqrt": sympy.sqrt,
    "cbrt": sympy.cbrt,
    "abs": sympy.Abs,
    "Abs": sympy.Abs,
    "sign": sympy.sign,
    "Min": sympy.Min,
    "Max": sympy.Max,
    "floor": sympy.floor,
    "ceiling": sympy.ceiling,
}

_BIN_OPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.Pow: lambda a, b: a**b,
}

_RESERVED = frozenset(CONSTANTS) | frozenset(FUNCTIONS)


class ExpressionError(ValueError):
    """The text is not an allowlisted mathematical expression."""


@dataclass(frozen=True)
class ParsedExpression:
    """The built SymPy expression plus what it referenced."""

    text: str
    expr: sympy.Expr
    symbols: frozenset[str]
    functions_used: frozenset[str]
    nodes: int


def parse_expression(
    text: object,
    *,
    symbols: set[str] | frozenset[str] | None = None,
) -> ParsedExpression:
    """Parse ``text`` into a SymPy expression using the allowlist only.

    ``symbols`` may predeclare free-variable names. A name that is neither a
    declared symbol, an allowlisted constant, nor an allowlisted function is
    rejected. If ``symbols`` is ``None`` any safe single identifier becomes a
    symbol, up to the symbol limit.
    """

    if not isinstance(text, str):
        raise ExpressionError("expression must be a string")
    cleaned = text.strip()
    if not cleaned:
        raise ExpressionError("expression is empty")
    if len(cleaned) > MAX_EXPRESSION:
        raise ExpressionError("expression is too long")
    if any(token in cleaned for token in (";", "\n", "\r", "\\", "__", "#", "`")):
        raise ExpressionError("expression contains a rejected character")
    if "=" in cleaned:
        raise ExpressionError("expression must not contain '='")

    allowed_names: set[str] = set(symbols) if symbols is not None else set()
    if symbols is not None:
        for name in allowed_names:
            if not name.isidentifier() or name.startswith("_") or name in _RESERVED:
                raise ExpressionError(f"declared symbol is not allowed: {name!r}")

    try:
        tree = ast.parse(cleaned, mode="eval")
    except (SyntaxError, ValueError) as exc:
        raise ExpressionError("expression is not valid syntax") from exc
    if not isinstance(tree, ast.Expression):
        raise ExpressionError("expression is not valid syntax")

    state = _State(predeclared=symbols is not None, allowed=allowed_names)
    expr = _build(tree.body, state, depth=0)
    if symbols is None and state.symbols and len(state.symbols) > MAX_SYMBOLS:
        raise ExpressionError("too many free symbols")
    return ParsedExpression(
        text=cleaned,
        expr=expr,
        symbols=frozenset(state.symbols),
        functions_used=frozenset(state.functions),
        nodes=state.nodes,
    )


class _State:
    __slots__ = ("allowed", "functions", "nodes", "predeclared", "symbols")

    def __init__(self, *, predeclared: bool, allowed: set[str]) -> None:
        self.predeclared = predeclared
        self.allowed = allowed
        self.symbols: set[str] = set()
        self.functions: set[str] = set()
        self.nodes = 0


def _tick(state: _State, depth: int) -> None:
    state.nodes += 1
    if state.nodes > MAX_NODES:
        raise ExpressionError("expression is too complex")
    if depth > MAX_DEPTH:
        raise ExpressionError("expression nests too deeply")


def _build(node: ast.AST, state: _State, *, depth: int) -> sympy.Expr:
    _tick(state, depth)

    if isinstance(node, ast.Constant):
        return _constant(node.value)

    if isinstance(node, ast.Name):
        return _name(node.id, state)

    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, (ast.UAdd, ast.USub)):
            value = _build(node.operand, state, depth=depth + 1)
            return value if isinstance(node.op, ast.UAdd) else -value
        raise ExpressionError("unary operator is not allowed")

    if isinstance(node, ast.BinOp):
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise ExpressionError("operator is not allowed")
        left = _build(node.left, state, depth=depth + 1)
        right = _build(node.right, state, depth=depth + 1)
        if isinstance(node.op, ast.Pow):
            return _safe_pow(left, right)
        return op(left, right)

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ExpressionError("only allowlisted functions may be called")
        if node.keywords:
            raise ExpressionError("keyword arguments are not allowed")
        if any(isinstance(arg, ast.Starred) for arg in node.args):
            raise ExpressionError("star arguments are not allowed")
        name = node.func.id
        function = FUNCTIONS.get(name)
        if function is None:
            raise ExpressionError(f"function is not allowed: {name!r}")
        state.functions.add(name)
        if len(state.functions) > MAX_CALLS:
            raise ExpressionError("too many function calls")
        if len(node.args) == 0:
            raise ExpressionError("function needs an argument")
        args = [_build(arg, state, depth=depth + 1) for arg in node.args]
        return function(*args)  # type: ignore[operator]

    raise ExpressionError(f"expression element is not allowed: {type(node).__name__}")


def _safe_pow(base: sympy.Expr, exponent: sympy.Expr) -> sympy.Expr:
    """Bound numeric powers so a small string cannot request a huge integer."""

    if not base.free_symbols and not exponent.free_symbols:
        try:
            power = int(exponent)
        except (TypeError, ValueError):
            power = None
        if power is not None:
            if abs(power) > _MAX_POW_EXPONENT:
                raise ExpressionError("exponent is too large")
            if power > 1 and base.is_number:
                numerator = abs(int(sympy.numer(base)))
                denominator = abs(int(sympy.denom(base)))
                bits = max(numerator.bit_length(), denominator.bit_length()) * power
                if bits > _MAX_POW_BITS:
                    raise ExpressionError("power result would be too large")
    return base**exponent


def _constant(value: object) -> sympy.Expr:
    if isinstance(value, bool):
        raise ExpressionError("booleans are not allowed")
    if isinstance(value, int):
        if value.bit_length() > MAX_INTEGER_BITS:
            raise ExpressionError("integer literal is too large")
        return sympy.Integer(value)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ExpressionError("non-finite numbers are not allowed")
        exact = sympy.Rational(str(value))
        if not isinstance(exact, sympy.Rational):
            raise ExpressionError("number literal is not rational")
        if abs(int(exact.p)).bit_length() > MAX_INTEGER_BITS:
            raise ExpressionError("number literal is too large")
        return exact
    raise ExpressionError("only integer and decimal literals are allowed")


def _name(name: str, state: _State) -> sympy.Expr:
    if name in CONSTANTS:
        return CONSTANTS[name]
    if name in FUNCTIONS:
        raise ExpressionError(f"function is not called: {name!r}")
    if name.startswith("_") or not name.isidentifier():
        raise ExpressionError(f"name is not allowed: {name!r}")
    if state.predeclared and name not in state.allowed:
        raise ExpressionError(f"undeclared symbol: {name!r}")
    if name not in state.symbols and len(state.symbols) >= MAX_SYMBOLS:
        raise ExpressionError("too many free symbols")
    state.symbols.add(name)
    return sympy.Symbol(name)
