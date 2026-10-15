"""Read a LaTeX relation as SymPy, with derivatives, integrals and matrices, and check it.

The scalar relation parser of :mod:`studium.authoring.grounding` refuses
differentials, integrals and matrices because reading ``du/dy`` as a product
makes it equal ``u/y``. This module reads them properly, or refuses:

* ``\\frac{d^n f}{dx^n}``, ``\\frac{\\partial f}{\\partial x}``, ``\\frac{d}{dx}(...)``,
  ``f'(x)`` and ``\\dot f`` become derivatives, but only of an expression that
  contains the variable, or of a function the paragraph has defined; the
  derivative of a bare symbol ``m`` with respect to ``t`` is refused because
  nothing says ``m`` depends on ``t``;
* ``\\int_a^b f\\,dx`` with numeric or symbolic limits is integrated;
* ``bmatrix``/``pmatrix`` literals take part in sums, products, transposes and
  inverses;
* the text is a hand-written recursive-descent parse that builds SymPy objects
  itself: nothing is evaluated, nothing is imported by name, and size, depth
  and time are bounded.

A relation that holds as an identity, with or without the definitions the
paragraph itself states, is reported as such; anything else is left unknown,
never false, except a constant difference between two explicit sides.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, TypeVar, cast

import sympy

from studium.verification.engine import VerificationTimeout, _run_bounded

MAX_TOKENS = 600
MAX_DEPTH = 28
MAX_OPS = 400
MAX_MATRIX = 6
_TIMEOUT = 6.0
_T = TypeVar("_T")


class Unsupported(ValueError):
    """The text uses notation this reader refuses to guess."""


_GREEK = frozenset(
    ["alpha", "beta", "gamma", "delta", "epsilon", "varepsilon", "zeta", "eta", "theta", "vartheta", "iota", "kappa", "lambda", "mu", "nu", "xi", "omicron", "rho", "varrho", "sigma", "tau", "upsilon", "phi", "varphi", "chi", "psi", "omega", "Gamma", "Delta", "Theta", "Lambda", "Xi", "Pi", "Sigma", "Upsilon", "Phi", "Psi", "Omega"]
)
_FUNCTIONS: dict[str, Callable[[Any], Any]] = {
    "sin": sympy.sin,
    "cos": sympy.cos,
    "tan": sympy.tan,
    "cot": sympy.cot,
    "sec": sympy.sec,
    "csc": sympy.csc,
    "arcsin": sympy.asin,
    "arccos": sympy.acos,
    "arctan": sympy.atan,
    "sinh": sympy.sinh,
    "cosh": sympy.cosh,
    "tanh": sympy.tanh,
    "exp": sympy.exp,
    "ln": sympy.log,
    "log": sympy.log,
}
_VECTOR_COMMANDS = frozenset({"mathbf", "boldsymbol", "vec", "bm"})
_NAME_COMMANDS = frozenset({"mathrm", "mathit", "text", "operatorname", "mathsf", "mathcal", "mathbb"})
_ACCENTS = frozenset({"bar", "hat", "tilde", "overline"})
_REFUSED = frozenset({"nabla", "sum", "prod", "lim", "oint", "iint", "iiint", "otimes", "wedge", "infty", "sup", "inf"})
_TRANSPOSE = frozenset({"T", "top", "intercal"})
_MATRIX_ENVS = frozenset({"bmatrix", "pmatrix", "matrix", "vmatrix", "Bmatrix", "Vmatrix"})

_TOKEN = re.compile(
    r"(?P<num>\d+(?:\.\d+)?)|(?P<cmd>\\[A-Za-z]+)|(?P<esc>\\[^A-Za-z])|(?P<name>[A-Za-z])|(?P<op>[-+*/^_=<>(){}\[\]|&',!:;.])|(?P<space>\s+)"
)


@dataclass(frozen=True)
class Token:
    kind: str
    text: str
    #: An explicit thin space (``\\,``, ``\\;``, ``\\:``) came just before this token.
    spaced: bool = False


@dataclass
class Definition:
    """``name = expr`` (or ``name(x) = expr``) stated earlier in the paragraph."""

    statement: str
    name: str
    variables: tuple[str, ...]
    expr: Any


@dataclass
class Outcome:
    """What a relation amounts to: ``identity``, ``contradiction`` or ``unknown``."""

    kind: str
    premises: tuple[str, ...] = ()
    detail: str = ""


@dataclass
class _Context:
    defs: dict[str, Definition] = field(default_factory=dict)
    used: set[str] = field(default_factory=set)
    discovered: dict[str, str] = field(default_factory=dict)
    functions: dict[str, str] = field(default_factory=dict)
    vectors: set[str] = field(default_factory=set)
    ops: int = 0
    decimals: bool = False
    calculus: bool = False


def tokenize(text: str) -> list[Token]:
    cleaned = text.replace("{,}", ".")
    cleaned = re.sub(r"(?<=\d)(?:\\[,;:!]|~)\s*(?=\d{3}(?!\d))", "", cleaned)
    cleaned = re.sub(r"\\(?:left|right|big|Big|bigg|Bigg)(?![A-Za-z])\s*", "", cleaned)
    # An explicit space ends the argument of a function written without parentheses: in
    # ``\\sin x\\,R`` the argument is ``x``. Mark it with a thin-space character.
    cleaned = re.sub(r"\\[,;:]", "\u2009", cleaned)
    cleaned = re.sub(r"\\!|~|\\q?quad(?![A-Za-z])", " ", cleaned)
    cleaned = re.sub(r"\\mathrm\s*\{\s*d\s*\}", "d", cleaned)
    cleaned = re.sub(r"\^\s*\{?\s*((?:\\prime\s*)+)\}?", lambda match: "'" * match.group(1).count("\\prime"), cleaned)
    tokens: list[Token] = []
    spaced = False
    for match in _TOKEN.finditer(cleaned):
        kind = match.lastgroup or ""
        if kind == "space":
            spaced = spaced or "\u2009" in match.group()
            continue
        tokens.append(Token(kind, match.group(), spaced))
        spaced = False
        if len(tokens) > MAX_TOKENS:
            raise Unsupported("the relation is too long")
    if sum(len(token.text) for token in tokens) != len("".join(cleaned.split())):
        raise Unsupported("the relation contains characters this reader does not know")
    return tokens


class _Parser:
    def __init__(self, tokens: list[Token], context: _Context, depth: int = 0) -> None:
        if depth > MAX_DEPTH:
            raise Unsupported("the relation nests too deeply")
        self.tokens = tokens
        self.index = 0
        self.context = context
        self.depth = depth

    # -- token helpers -------------------------------------------------------------------------
    def peek(self, offset: int = 0) -> Token | None:
        position = self.index + offset
        return self.tokens[position] if position < len(self.tokens) else None

    def take(self) -> Token:
        token = self.peek()
        if token is None:
            raise Unsupported("unexpected end of the relation")
        self.index += 1
        return token

    def at_op(self, text: str) -> bool:
        token = self.peek()
        return token is not None and token.kind == "op" and token.text == text

    def expect_op(self, text: str) -> None:
        token = self.take()
        if token.kind != "op" or token.text != text:
            raise Unsupported(f"expected '{text}'")

    def done(self) -> bool:
        return self.index >= len(self.tokens)

    def count(self, amount: int = 1) -> None:
        self.context.ops += amount
        if self.context.ops > MAX_OPS:
            raise Unsupported("the relation is too large")

    def sub(self, tokens: list[Token]) -> _Parser:
        return _Parser(tokens, self.context, self.depth + 1)

    def group(self) -> list[Token]:
        """The tokens of the next ``{...}`` group, without the braces."""

        self.expect_op("{")
        depth = 1
        start = self.index
        while self.index < len(self.tokens):
            token = self.tokens[self.index]
            if token.kind == "op" and token.text == "{":
                depth += 1
            elif token.kind == "op" and token.text == "}":
                depth -= 1
                if depth == 0:
                    inner = self.tokens[start : self.index]
                    self.index += 1
                    return inner
            self.index += 1
        raise Unsupported("unbalanced braces")

    def argument(self) -> list[Token]:
        """A brace group, or the single next token (``x^2``, ``\\frac12``)."""

        if self.at_op("{"):
            return self.group()
        return [self.take()]

    # -- grammar -------------------------------------------------------------------------------
    def parse_all(self) -> Any:
        value = self.parse_sum()
        if not self.done():
            raise Unsupported("unexpected text after the expression")
        return value

    def parse_sum(self) -> Any:
        value = self.parse_term()
        while self.at_op("+") or self.at_op("-"):
            sign = self.take().text
            right = self.parse_term()
            self.count()
            value = value + right if sign == "+" else value - right
        return value

    def starts_factor(self) -> bool:
        token = self.peek()
        if token is None:
            return False
        if token.kind in {"num", "name"}:
            return True
        if token.kind == "op":
            return token.text in {"(", "[", "{", "|"}
        if token.kind == "cmd":
            command = token.text[1:]
            return command not in {"cdot", "times", "div", "pm", "mp", "ldots", "cdots", "dots", "le", "ge", "leq", "geq"}
        return False

    def parse_term(self) -> Any:
        value = self.parse_unary()
        while True:
            if self.at_op("*") or (self.peek() and self.peek().text in {"\\cdot", "\\times"}):  # type: ignore[union-attr]
                self.take()
                right = self.parse_unary()
                value = self.multiply(value, right)
            elif self.at_op("/"):
                self.take()
                right = self.parse_unary()
                self.count()
                if isinstance(right, sympy.MatrixBase):
                    raise Unsupported("division by a matrix")
                value = value / right
            elif self.starts_factor() and not self.at_op("|"):
                right = self.parse_unary()
                value = self.multiply(value, right)
            else:
                return value

    def multiply(self, left: Any, right: Any) -> Any:
        self.count()
        return left * right

    def parse_unary(self) -> Any:
        if self.at_op("-"):
            self.take()
            return -self.parse_unary()
        if self.at_op("+"):
            self.take()
            return self.parse_unary()
        return self.parse_power()

    def parse_power(self) -> Any:
        base = self.parse_atom()
        while True:
            if self.at_op("'"):
                self.take()
                base = self.prime(base)
                continue
            if self.at_op("^"):
                self.take()
                exponent_tokens = self.argument()
                base = self.power(base, exponent_tokens)
                continue
            return base

    def power(self, base: Any, tokens: list[Token]) -> Any:
        texts = [token.text for token in tokens]
        flat = "".join(text.lstrip("\\") for text in texts if text not in {"{", "}"})
        if flat in _TRANSPOSE or flat in {"mathsfT", "mathrmT"}:
            if isinstance(base, sympy.MatrixBase):
                return base.T
            raise Unsupported("a transpose of something that is not a matrix")
        if texts == ["\\circ"]:
            if isinstance(base, sympy.MatrixBase):
                raise Unsupported("degrees of a matrix")
            return base * sympy.pi / 180
        if len(texts) == 1 and texts[0] in {"*", "\\ast", "\\star", "\\prime"}:
            return self.decorate(base, "star" if texts[0] != "\\prime" else "prime")
        exponent = self.sub(tokens).parse_all()
        self.count()
        if isinstance(base, sympy.MatrixBase):
            if exponent == -1:
                try:
                    return base.inv()
                except Exception as error:
                    raise Unsupported("the matrix is not invertible") from error
            if isinstance(exponent, sympy.Integer) and 0 <= int(exponent) <= 6:
                return base**exponent
            raise Unsupported("unsupported matrix power")
        if isinstance(exponent, sympy.MatrixBase):
            raise Unsupported("a matrix exponent")
        if exponent.is_Rational is not True and exponent.free_symbols == set():
            return sympy.Pow(base, exponent)
        return base**exponent

    def decorate(self, base: Any, suffix: str) -> Any:
        if isinstance(base, sympy.Symbol):
            return sympy.Symbol(f"{base.name}_{suffix}")
        raise Unsupported("a decoration on something that is not a name")

    def prime(self, base: Any) -> Any:
        """``w'`` or ``w'(x)``: the derivative of a defined function in its variable."""

        if isinstance(base, sympy.core.function.AppliedUndef) and base.func.__name__ in self.context.functions:
            variable = sympy.Symbol(self.context.functions[base.func.__name__])
            return sympy.diff(base, variable)
        if isinstance(base, sympy.Symbol) and base.name in self.context.defs:
            definition = self.context.defs[base.name]
            if len(definition.variables) == 1:
                return sympy.diff(definition.expr, sympy.Symbol(definition.variables[0]))
        raise Unsupported("a prime on a name that is not a defined function")

    # -- atoms ---------------------------------------------------------------------------------
    def parse_atom(self) -> Any:
        token = self.take()
        if token.kind == "num":
            self.count()
            if "." in token.text:
                self.context.decimals = True
            return sympy.Rational(token.text)
        if token.kind == "name":
            return self.name_atom(token.text)
        if token.kind == "op":
            if token.text == "(":
                value = self.parse_sum()
                if self.at_op(","):
                    raise Unsupported("a coordinate list")
                self.expect_op(")")
                return value
            if token.text == "[":
                value = self.parse_sum()
                self.expect_op("]")
                return value
            if token.text == "{":
                self.index -= 1
                return self.sub(self.group()).parse_all()
            if token.text == "|":
                value = self.parse_sum()
                self.expect_op("|")
                if isinstance(value, sympy.MatrixBase):
                    raise Unsupported("a norm or determinant")
                return sympy.Abs(value)
        if token.kind == "cmd":
            return self.command(token.text[1:])
        raise Unsupported(f"unexpected '{token.text}'")

    def name_atom(self, letter: str) -> Any:
        name = letter + self.subscript()
        return self.symbol_or_function(name)

    def subscript(self) -> str:
        if not self.at_op("_"):
            return ""
        self.take()
        inner = self.argument()
        text = "".join(token.text.lstrip("\\") for token in inner if token.text not in {"{", "}"})
        text = re.sub(r"^(?:mathrm|text|mathit|operatorname)(?=[A-Za-z])", "", text)
        if not re.fullmatch(r"[A-Za-z0-9+\-]{1,16}", text):
            raise Unsupported("an unreadable subscript")
        return "_" + text

    def symbol_or_function(self, name: str, *, vector: bool = False) -> Any:
        key = name + ("_vec" if vector else "")
        if vector:
            self.context.vectors.add(key)
        defined = self.context.defs.get(key)
        if self.at_op("'"):
            return self.primed(key)
        # A name applied to an argument: a defined function of one variable, a discovered function, or
        # a function value such as u(0). A name defined without variables followed by '(' is a product.
        if self.at_op("(") and ((defined is not None and defined.variables) or (defined is None and key in self.context.functions)):
            return self.apply(key)
        if defined is not None:
            self.context.used.add(defined.statement)
            return defined.expr
        if key in self.context.functions:
            return sympy.Function(key)(sympy.Symbol(self.context.functions[key]))
        if self.at_op("("):
            inside, after = self.peek(1), self.peek(2)
            if inside is not None and inside.kind in {"name", "num"} and after is not None and after.kind == "op" and after.text == ")":
                # u(0), w(L), M(x): a value of a function, not the product of u and 0. Opaque, never evaluated.
                self.take()
                argument = self.parse_sum()
                self.expect_op(")")
                return sympy.Function(key)(argument)
        return sympy.Symbol(key)

    def primed(self, key: str) -> Any:
        """``w'``, ``w''(x)``: the derivative of a defined or discovered function of one variable."""

        order = 0
        while self.at_op("'"):
            self.take()
            order += 1
        definition = self.context.defs.get(key)
        argument: Any = None
        variable_name: str | None = None
        if self.at_op("("):
            after = self.peek(2)
            inside = self.peek(1)
            if after is not None and after.kind == "op" and after.text == ")" and inside is not None and inside.kind == "name":
                variable_name = inside.text
            self.expect_op("(")
            argument = self.parse_sum()
            self.expect_op(")")
        if definition is not None:
            if len(definition.variables) != 1:
                raise Unsupported("a prime on a name that is not a function of one variable")
            self.context.used.add(definition.statement)
            variable = sympy.Symbol(definition.variables[0])
            if variable not in definition.expr.free_symbols:
                raise Unsupported("nothing says the function depends on its variable")
            value = sympy.diff(definition.expr, variable, order)
            return value if argument is None else value.subs(variable, argument)
        name = self.context.functions.get(key) or variable_name
        if name is None:
            raise Unsupported("a prime on a name whose variable is not stated")
        if key not in self.context.functions:
            self.context.discovered[key] = name
            self.context.functions[key] = name
        variable = sympy.Symbol(name)
        value = sympy.diff(sympy.Function(key)(variable), variable, order)
        return value if argument is None or argument == variable else value.subs(variable, argument)

    def apply(self, key: str) -> Any:
        self.expect_op("(")
        value = self.parse_sum()
        self.expect_op(")")
        if key in self.context.defs:
            definition = self.context.defs[key]
            self.context.used.add(definition.statement)
            if len(definition.variables) != 1:
                raise Unsupported("a function of several variables")
            return definition.expr.subs(sympy.Symbol(definition.variables[0]), value)
        return sympy.Function(key)(value)

    def command(self, command: str) -> Any:
        if command in _REFUSED:
            raise Unsupported(f"\\{command} is not read")
        if command in {"frac", "dfrac", "tfrac"}:
            return self.fraction()
        if command == "sqrt":
            return self.root()
        if command == "ell":
            return self.name_atom("ell")
        if command == "Delta":
            return self.delta()
        if command in _GREEK:
            return self.name_atom("\\" + command)
        if command == "pi":
            return sympy.pi
        if command in _FUNCTIONS:
            return self.function(command)
        if command in {"dot", "ddot"}:
            return self.dotted(2 if command == "ddot" else 1)
        if command in _VECTOR_COMMANDS:
            return self.styled(vector=True)
        if command in _NAME_COMMANDS:
            return self.styled(vector=False)
        if command in _ACCENTS:
            tokens = self.argument()
            return self.decorate(self.sub(tokens).parse_all(), command)
        if command == "int":
            return self.integral()
        if command == "partial":
            raise Unsupported("a stray partial derivative sign")
        if command == "begin":
            return self.matrix()
        raise Unsupported(f"\\{command} is not read")

    def delta(self) -> Any:
        """``\\Delta p`` is one quantity, the change of ``p``, not the product of two symbols."""

        token = self.peek()
        if token is None:
            raise Unsupported("a Delta with nothing after it")
        if token.kind == "name":
            self.take()
            return self.symbol_or_function("Delta_" + token.text + self.subscript())
        if token.kind == "cmd" and token.text[1:] in _GREEK:
            self.take()
            return self.symbol_or_function("Delta_" + token.text[1:] + self.subscript())
        raise Unsupported("a Delta before something that is not a name")

    def styled(self, *, vector: bool) -> Any:
        tokens = self.argument()
        text = "".join(token.text.lstrip("\\") for token in tokens)
        if not re.fullmatch(r"[A-Za-z0-9_]{1,16}", text.replace("{", "").replace("}", "")):
            raise Unsupported("an unreadable name")
        name = text + self.subscript()
        return self.symbol_or_function(name, vector=vector)

    def dotted(self, order: int) -> Any:
        tokens = self.argument()
        name = "".join(token.text.lstrip("\\") for token in tokens)
        name = name + self.subscript()
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name):
            raise Unsupported("an unreadable dotted name")
        if name not in self.context.functions and name not in self.context.defs:
            self.context.discovered[name] = "t"
        self.context.functions.setdefault(name, "t")
        if name in self.context.functions and self.context.functions[name] != "t":
            raise Unsupported("a time derivative of a name that depends on another variable")
        return self.derivative_of_name(name, [("t", order)])

    def function(self, command: str) -> Any:
        base: Any = None
        if command == "log" and self.at_op("_"):
            self.take()
            base = self.sub(self.argument()).parse_all()
        power: Any = None
        if self.at_op("^"):
            self.take()
            power = self.sub(self.argument()).parse_all()
        if self.at_op("("):
            self.take()
            argument = self.parse_sum()
            self.expect_op(")")
        else:
            argument = self.parse_power_arg()
        if isinstance(argument, sympy.MatrixBase):
            raise Unsupported("a function of a matrix")
        self.count()
        value = sympy.log(argument, base) if base is not None else _FUNCTIONS[command](argument)
        return value**power if power is not None else value

    def parse_power_arg(self) -> Any:
        """The argument of ``\\sin x``: a unary run of factors up to the next sum or product sign."""

        value = self.parse_power()
        while self.starts_factor() and not self.at_op("|") and not self.at_op("("):
            token = self.peek()
            if token is not None and token.kind == "cmd" and token.text[1:] in _FUNCTIONS:
                break
            if token is not None and token.spaced:
                break
            value = value * self.parse_power()
        return value

    def root(self) -> Any:
        index: Any = 2
        if self.at_op("["):
            self.take()
            start = self.index
            while not self.at_op("]"):
                self.take()
            inner = self.tokens[start : self.index]
            self.expect_op("]")
            index = self.sub(inner).parse_all()
        radicand = self.sub(self.group()).parse_all()
        if isinstance(radicand, sympy.MatrixBase):
            raise Unsupported("a root of a matrix")
        self.count()
        return sympy.Pow(radicand, sympy.Rational(1) / index) if index != 2 else sympy.sqrt(radicand)

    # -- derivatives ---------------------------------------------------------------------------
    def fraction_arguments(self) -> tuple[list[Token], list[Token]]:
        """``\\frac{a}{b}``, ``\\frac12`` (digit shorthand) or ``\\frac a b``."""

        first = self.peek()
        if first is not None and first.kind == "num" and len(first.text) == 2 and "." not in first.text:
            self.take()
            return [Token("num", first.text[0])], [Token("num", first.text[1])]
        return self.argument(), self.argument()

    def fraction(self) -> Any:
        numerator, denominator = self.fraction_arguments()
        derivative = self.derivative_orders(denominator)
        operand = self.derivative_operand(numerator, derivative)
        if derivative is not None:
            order_variables, _count = derivative
            if operand is not None and operand == []:
                return self.derivative_of_following(order_variables)
            return self.derivative(operand or [], order_variables)
        top = self.sub(numerator).parse_all()
        bottom = self.sub(denominator).parse_all()
        if isinstance(bottom, sympy.MatrixBase):
            raise Unsupported("division by a matrix")
        self.count()
        return top / bottom

    @staticmethod
    def derivative_orders(denominator: list[Token]) -> tuple[list[tuple[str, int]], int] | None:
        """``dx^n`` / ``\\partial x \\partial y`` in a denominator as ``[(variable, order)]``."""

        variables: list[tuple[str, int]] = []
        index = 0
        while index < len(denominator):
            token = denominator[index]
            is_d = (token.kind == "name" and token.text == "d") or token.text == "\\partial"
            if not is_d or index + 1 >= len(denominator):
                return None
            variable = denominator[index + 1]
            if variable.kind != "name":
                return None
            name = variable.text
            index += 2
            while index + 1 < len(denominator) and denominator[index].text == "_":
                suffix = denominator[index + 1]
                if suffix.text == "{":
                    return None
                name += "_" + suffix.text.lstrip("\\")
                index += 2
            order = 1
            if index < len(denominator) and denominator[index].text == "^":
                index += 1
                if index >= len(denominator):
                    return None
                if denominator[index].text == "{":
                    if index + 2 >= len(denominator) or denominator[index + 2].text != "}":
                        return None
                    order_token = denominator[index + 1]
                    index += 3
                else:
                    order_token = denominator[index]
                    index += 1
                if order_token.kind != "num":
                    return None
                order = int(order_token.text)
            variables.append((name, order))
        if not variables:
            return None
        return variables, sum(order for _name, order in variables)

    def derivative_operand(self, numerator: list[Token], derivative: tuple[list[tuple[str, int]], int] | None) -> list[Token] | None:
        """The numerator after its leading ``d``/``\\partial`` and optional order, or ``None`` if not a derivative."""

        if derivative is None or not numerator:
            return None
        first = numerator[0]
        if not ((first.kind == "name" and first.text == "d") or first.text == "\\partial"):
            return None
        index = 1
        if index < len(numerator) and numerator[index].text == "^":
            index += 1
            if index < len(numerator) and numerator[index].text == "{":
                if index + 2 < len(numerator) and numerator[index + 2].text == "}":
                    index += 3
                else:
                    return None
            else:
                index += 1
        return numerator[index:]

    def derivative_of_following(self, variables: list[tuple[str, int]]) -> Any:
        """``\\frac{d}{dx}`` applied to the next factor, which must be a group or a single atom."""

        token = self.peek()
        if token is None or not (
            token.kind in {"num", "name"} or (token.kind == "op" and token.text in {"(", "["}) or token.text in {"\\sin", "\\cos"}
        ):
            raise Unsupported("a derivative operator with nothing to differentiate")
        operand = self.parse_power()
        return self.derivative_value(operand, variables)

    def derivative(self, operand: list[Token], variables: list[tuple[str, int]]) -> Any:
        if not operand:
            raise Unsupported("a derivative with nothing to differentiate")
        # A bare name is a function of the variable: defined earlier, or discovered from this derivative.
        if operand[0].kind == "name" and self.is_bare_name(operand):
            name = self.bare_name(operand)
            self.discover(name, variables)
        elif operand[0].kind == "cmd" and operand[0].text[1:] in _VECTOR_COMMANDS | _NAME_COMMANDS | _GREEK:
            probe = self.sub(operand)
            value = probe.parse_all()
            if isinstance(value, sympy.Symbol):
                self.discover(value.name, variables)
        return self.derivative_value(self.sub(operand).parse_all(), variables)

    def discover(self, name: str, variables: list[tuple[str, int]]) -> None:
        if len(variables) == 1 and name not in self.context.defs and name not in self.context.functions:
            self.context.discovered[name] = variables[0][0]
            self.context.functions[name] = variables[0][0]

    @staticmethod
    def is_bare_name(tokens: list[Token]) -> bool:
        index = 1
        while index + 1 < len(tokens) and tokens[index].text == "_":
            index += 2
        return index == len(tokens)

    @staticmethod
    def bare_name(tokens: list[Token]) -> str:
        name = tokens[0].text
        index = 1
        while index + 1 < len(tokens) and tokens[index].text == "_":
            name += "_" + tokens[index + 1].text.lstrip("\\")
            index += 2
        return name

    def derivative_value(self, operand: Any, variables: list[tuple[str, int]]) -> Any:
        if isinstance(operand, sympy.MatrixBase):
            raise Unsupported("a derivative of a matrix")
        self.context.calculus = True
        result = operand
        for name, order in variables:
            variable = sympy.Symbol(name)
            if variable not in result.free_symbols and not _contains_function_of(result, variable):
                raise Unsupported(f"nothing says the operand depends on {name}")
            self.count(order)
            result = sympy.diff(result, variable, order)
        return result

    def derivative_of_name(self, name: str, variables: list[tuple[str, int]]) -> Any:
        if name in self.context.defs:
            self.context.used.add(self.context.defs[name].statement)
            return self.derivative_value(self.context.defs[name].expr, variables)
        variable = sympy.Symbol(variables[0][0])
        function = sympy.Function(name)(variable)
        return sympy.diff(function, variable, variables[0][1])

    # -- integrals -----------------------------------------------------------------------------
    def integral(self) -> Any:
        lower: Any = None
        upper: Any = None
        for _ in range(2):
            if self.at_op("_"):
                self.take()
                lower = self.sub(self.argument()).parse_all()
            elif self.at_op("^"):
                self.take()
                upper = self.sub(self.argument()).parse_all()
        if lower is None or upper is None:
            raise Unsupported("an indefinite integral")
        end = self.find_differential()
        body = self.tokens[self.index : end]
        variable_token = self.tokens[end + 1]
        self.index = end + 2
        variable = sympy.Symbol(variable_token.text)
        self.context.functions.pop("", None)
        value = self.sub(body).parse_all()
        if isinstance(value, sympy.MatrixBase):
            raise Unsupported("an integral of a matrix")
        self.count(8)
        self.context.calculus = True
        if sympy.count_ops(value) > 60:
            raise Unsupported("the integrand is too large")
        try:
            result = _run_bounded(lambda: sympy.integrate(value, (variable, lower, upper)), _TIMEOUT)
        except (VerificationTimeout, Exception) as error:
            raise Unsupported("the integral did not complete") from error
        if result.has(sympy.Integral):
            raise Unsupported("the integral has no closed form here")
        return result

    def find_differential(self) -> int:
        depth = 0
        for position in range(self.index, len(self.tokens) - 1):
            token = self.tokens[position]
            if token.kind == "op" and token.text in "({[":
                depth += 1
            elif token.kind == "op" and token.text in ")}]":
                depth -= 1
            elif depth == 0 and position > self.index and token.kind == "name" and token.text == "d":
                following = self.tokens[position + 1]
                if following.kind == "name" or (following.kind == "cmd" and following.text[1:] in _GREEK):
                    return position
        raise Unsupported("an integral without a differential")

    # -- matrices ------------------------------------------------------------------------------
    def matrix(self) -> Any:
        environment = "".join(token.text for token in self.group())
        if environment not in _MATRIX_ENVS:
            raise Unsupported("an unsupported environment")
        start = self.index
        depth = 0
        end = None
        for position in range(self.index, len(self.tokens)):
            token = self.tokens[position]
            if token.kind == "cmd" and token.text == "\\begin":
                depth += 1
            elif token.kind == "cmd" and token.text == "\\end":
                if depth == 0:
                    end = position
                    break
                depth -= 1
        if end is None:
            raise Unsupported("an unterminated matrix")
        body = self.tokens[start:end]
        self.index = end + 1
        closing = self.group()
        if "".join(token.text for token in closing) != environment:
            raise Unsupported("a mismatched matrix environment")
        rows: list[list[Any]] = [[]]
        cell: list[Token] = []
        nesting = 0
        for token in body:
            if token.kind in {"cmd"} and token.text == "\\begin":
                nesting += 1
            if token.kind == "cmd" and token.text == "\\end":
                nesting -= 1
            if nesting == 0 and token.kind == "op" and token.text == "&":
                rows[-1].append(self.cell(cell))
                cell = []
            elif nesting == 0 and token.kind == "esc" and token.text == "\\\\":
                rows[-1].append(self.cell(cell))
                cell = []
                rows.append([])
            else:
                cell.append(token)
        if cell or rows[-1]:
            rows[-1].append(self.cell(cell))
        rows = [row for row in rows if row]
        if not rows or len(rows) > MAX_MATRIX or len({len(row) for row in rows}) != 1 or len(rows[0]) > MAX_MATRIX:
            raise Unsupported("an unsupported matrix shape")
        self.count(len(rows) * len(rows[0]))
        return sympy.Matrix(rows)

    def cell(self, tokens: list[Token]) -> Any:
        if not tokens:
            raise Unsupported("an empty matrix entry")
        value = self.sub(tokens).parse_all()
        if isinstance(value, sympy.MatrixBase):
            raise Unsupported("a nested matrix")
        return value


def _contains_function_of(expression: Any, variable: Any) -> bool:
    return any(variable in application.args for application in expression.atoms(sympy.core.function.AppliedUndef))


def _parse_side(text: str, context: _Context) -> Any:
    tokens = tokenize(text)
    if not tokens:
        raise Unsupported("an empty side")
    return _Parser(tokens, context).parse_all()


def _split_relation(statement: str) -> tuple[str, str]:
    depth = 0
    cut: int | None = None
    index = 0
    while index < len(statement):
        character = statement[index]
        if character in "{(":
            depth += 1
        elif character in "})":
            depth -= 1
        elif character == "\\" and statement[index : index + 6] == "\\begin":
            depth += 1
        elif character == "\\" and statement[index : index + 4] == "\\end":
            depth -= 1
        elif character == "=" and depth == 0:
            if cut is not None:
                raise Unsupported("a chain of relations")
            cut = index
        index += 1
    if cut is None:
        raise Unsupported("not a relation")
    return statement[:cut], statement[cut + 1 :]


def _check_vectors(expressions: list[Any], vectors: set[str]) -> None:
    """Bold symbols stand for vectors: they may only be added and scaled, never multiplied together."""

    if not vectors:
        return
    symbols = [sympy.Symbol(name) for name in sorted(vectors)]
    for expression in expressions:
        if isinstance(expression, sympy.MatrixBase):
            raise Unsupported("a vector and a matrix in one relation")
        try:
            degree = sympy.Poly(sympy.expand(expression), *symbols).total_degree()
        except sympy.PolynomialError as error:
            raise Unsupported("vectors are multiplied or divided") from error
        if degree > 1:
            raise Unsupported("vectors are multiplied or divided")


def _prepare(statement: str, defs: dict[str, Definition]) -> tuple[Any, Any, _Context]:
    left_text, right_text = _split_relation(statement)
    functions: dict[str, str] = {}
    for _attempt in range(2):
        context = _Context(defs=defs, functions=dict(functions))
        left = _parse_side(left_text, context)
        right = _parse_side(right_text, context)
        if not context.discovered:
            _check_vectors([left, right] if not isinstance(left, sympy.MatrixBase) else [], context.vectors)
            return left, right, context
        functions = dict(context.functions)
    raise Unsupported("the functions of this relation could not be settled")


def _zero(difference: Any) -> bool:
    if isinstance(difference, sympy.MatrixBase):
        return all(_expression_zero(entry) for entry in difference)
    return _expression_zero(difference)


def _expression_zero(expression: Any) -> bool:
    if expression == 0:
        return True
    if sympy.count_ops(expression) > MAX_OPS:
        return False
    try:
        for step in (sympy.expand, lambda e: sympy.cancel(sympy.together(sympy.expand(e)))):
            reduced = _run_bounded(lambda step=step: step(expression), _TIMEOUT)  # type: ignore[misc]
            if reduced == 0:
                return True
        if sympy.count_ops(expression) <= 120:
            return _run_bounded(lambda: sympy.simplify(expression), _TIMEOUT) == 0
    except Exception:
        return False
    return False


def check_relation(statement: str, defs: dict[str, Definition] | None = None) -> Outcome | None:
    """``None`` when the relation is not read; otherwise whether it is an identity, a contradiction or unknown."""

    try:
        left, right, context = _prepare(statement, defs or {})
    except Unsupported:
        return None
    except (sympy.SympifyError, TypeError, ValueError, ZeroDivisionError, RecursionError, AttributeError):
        return None
    premises = tuple(sorted(context.used))
    try:
        if isinstance(left, sympy.MatrixBase) != isinstance(right, sympy.MatrixBase):
            return Outcome("unknown", premises, "a matrix against a scalar")
        if isinstance(left, sympy.MatrixBase):
            if left.shape != right.shape:
                return Outcome("contradiction", premises, "the shapes differ")
            difference = left - right
        else:
            difference = left - right
        if _zero(difference):
            return Outcome("identity", premises, "")
        if not isinstance(difference, sympy.MatrixBase) and not context.decimals:
            # A decimal literal may be a rounded value (6.26 for 6.2642...): never a contradiction.
            constant = sympy.simplify(difference) if sympy.count_ops(difference) <= 60 else difference
            if constant.is_number and constant.free_symbols == set() and constant != 0 and constant.is_real is not False:
                return Outcome("contradiction", premises, f"the sides differ by {constant}")
    except Exception:
        return None
    # Both sides must be explicit expressions of the same quantities: "U = integral(...)" defines U, it is not
    # a claim that two expressions coincide.
    if (
        context.calculus
        and not context.decimals
        and not isinstance(difference, sympy.MatrixBase)
        and left.free_symbols == right.free_symbols
    ):
        detail = _differs_numerically(difference)
        if detail is not None:
            return Outcome("contradiction", premises, detail)
    return Outcome("unknown", premises, "")


_SAMPLES = (sympy.Rational(3, 2), sympy.Rational(5, 3), sympy.Rational(7, 4), sympy.Rational(9, 5))


def _differs_numerically(difference: Any) -> str | None:
    """Evidence that two explicit sides of a computed relation are not equal: they differ at every sample point.

    Only for relations with a derivative or an integral on explicit sides: a stated computation whose
    result does not match the closed form. The samples are fixed positive rationals, and every
    evaluation must be a finite real number, so an unevaluable or accidental zero gives no verdict.
    """

    symbols = sorted(difference.free_symbols, key=str)
    if not symbols or len(symbols) > 8 or sympy.count_ops(difference) > MAX_OPS or difference.has(sympy.core.function.AppliedUndef):
        return None
    for offset in range(len(_SAMPLES)):
        point = {symbol: _SAMPLES[(index + offset) % len(_SAMPLES)] + index for index, symbol in enumerate(symbols)}
        try:
            value = _run_bounded(lambda point=point: sympy.N(difference.subs(point), 30), _TIMEOUT)  # type: ignore[misc]
        except Exception:
            return None
        if not value.is_real or not value.is_finite or abs(value) < sympy.Float("1e-12"):
            return None
    return "the computed side differs from the stated side at every sample point"


def as_definition(statement: str, defs: dict[str, Definition]) -> Definition | None:
    """A relation ``name = explicit expression`` (or ``name(x) = ...``) that later relations may use."""

    try:
        left_text, right_text = _split_relation(statement)
    except Unsupported:
        return None
    try:
        tokens = tokenize(left_text) if left_text.strip() else []
    except Unsupported:
        return None
    if not tokens:
        return None
    try:
        name, variables = _definition_target(tokens)
    except Unsupported:
        return None
    try:
        context = _Context(defs=defs)
        value = _parse_side(right_text, context)
    except (Unsupported, sympy.SympifyError, TypeError, ValueError, ZeroDivisionError, RecursionError, AttributeError):
        return None
    if context.discovered:
        return None
    if isinstance(value, sympy.MatrixBase):
        if name in {symbol.name for symbol in value.free_symbols}:
            return None
        return Definition(statement=statement, name=name, variables=variables, expr=value)
    if not value.free_symbols and not variables:
        return None
    if value.has(sympy.core.function.AppliedUndef) or name in {symbol.name for symbol in value.free_symbols}:
        return None
    if not variables and context.vectors:
        return None
    return Definition(statement=statement, name=name, variables=variables, expr=value)


def _definition_target(tokens: list[Token]) -> tuple[str, tuple[str, ...]]:
    """``w`` / ``w_{1}`` / ``w(x)`` / ``\\mathbf{K}`` as a definition target: its name and variables."""

    name = ""
    index = 0
    first = tokens[0]
    if first.kind == "name" or (first.kind == "cmd" and first.text[1:] in _GREEK):
        name = first.text
        index = 1
    elif first.kind == "cmd" and first.text[1:] in _VECTOR_COMMANDS | _NAME_COMMANDS and len(tokens) >= 4:
        inner = tokens[2].text.lstrip("\\")
        if tokens[1].text != "{" or tokens[3].text != "}" or not re.fullmatch(r"[A-Za-z0-9]+", inner):
            raise Unsupported("an unreadable definition target")
        name = inner + ("_vec" if first.text[1:] in _VECTOR_COMMANDS else "")
        index = 4
    else:
        raise Unsupported("not a definition target")
    while index + 1 < len(tokens) and tokens[index].text == "_":
        if tokens[index + 1].text == "{":
            end = next((position for position in range(index + 2, len(tokens)) if tokens[position].text == "}"), None)
            if end is None:
                raise Unsupported("unbalanced subscript")
            name += "_" + "".join(token.text.lstrip("\\") for token in tokens[index + 2 : end])
            index = end + 1
        else:
            name += "_" + tokens[index + 1].text.lstrip("\\")
            index += 2
    if index == len(tokens):
        return name, ()
    if tokens[index].text == "(" and tokens[-1].text == ")":
        inside = tokens[index + 1 : -1]
        if len(inside) == 1 and inside[0].kind == "name":
            return name, (inside[0].text,)
    raise Unsupported("not a definition target")


@lru_cache(maxsize=2048)
def _cached(statement: str, premise_key: tuple[tuple[str, str], ...]) -> Outcome | None:
    defs: dict[str, Definition] = {}
    for text, _name in premise_key:
        definition = as_definition(text, defs)
        if definition is not None:
            defs[definition.name] = definition
    return check_relation(statement, defs)


def check_with_premises(statement: str, premises: list[Definition]) -> Outcome | None:
    """``check_relation`` with the definitions the paragraph stated earlier (memoized)."""

    key = tuple((definition.statement, definition.name) for definition in premises)
    return cast(Outcome | None, _cached(statement, key))
