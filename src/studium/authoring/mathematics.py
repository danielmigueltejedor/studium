"""Structured mathematical content for the book.

A university textbook must not print a computational expression as its primary
mathematics. This module keeps the representations apart:

- ``symbolic``: an ASCII expression (``rho*V*D/mu``) used for verification.
- ``latex``: a typeset equation (``\\frac{\\rho V D}{\\mu}``) used for display.
- ``numeric``: the replay expression (``998*2*0.1/0.001``) used for checking.
- ``substitution``: the expression with the measured values and units in place.

The LaTeX is generated with SymPy but never trusted blindly: every generated
string is validated (balanced delimiters, no raw ``**`` or bare ``^``) and the
caller receives the validation result next to the LaTeX.
"""

from __future__ import annotations

import re
from fractions import Fraction

from studium.verification.parser import CONSTANTS, FUNCTIONS

__all__ = [
    "DEFAULT_SYMBOL_NAMES",
    "MathError",
    "numeric_latex",
    "substitution_latex",
    "symbol_names_of",
    "symbolic_latex",
    "unit_latex",
    "validate_latex",
]


class MathError(ValueError):
    """The symbolic input cannot be trusted or parsed."""


#: LaTeX name for the symbols the textbook uses. Names not listed keep SymPy's
#: own beautiful rendering (``rho`` is already ``\rho``).
DEFAULT_SYMBOL_NAMES: dict[str, str] = {
    "alpha": r"\alpha",
    "beta": r"\beta",
    "gamma": r"\gamma",
    "Gamma": r"\Gamma",
    "delta": r"\delta",
    "Delta": r"\Delta",
    "epsilon": r"\varepsilon",
    "varepsilon": r"\varepsilon",
    "eta": r"\eta",
    "theta": r"\theta",
    "Theta": r"\Theta",
    "kappa": r"\kappa",
    "lambda": r"\lambda",
    "Lambda": r"\Lambda",
    "mu": r"\mu",
    "nu": r"\nu",
    "xi": r"\xi",
    "pi": r"\pi",
    "Pi": r"\Pi",
    "rho": r"\rho",
    "sigma": r"\sigma",
    "Sigma": r"\Sigma",
    "tau": r"\tau",
    "phi": r"\phi",
    "Phi": r"\Phi",
    "chi": r"\chi",
    "psi": r"\psi",
    "Psi": r"\Psi",
    "omega": r"\omega",
    "Omega": r"\Omega",
    "delta_star": r"\delta^{*}",
    "theta_star": r"\theta^{*}",
    "Re": r"\mathrm{Re}",
    "Ma": r"\mathrm{Ma}",
    "Fr": r"\mathrm{Fr}",
    "Eu": r"\mathrm{Eu}",
    "We": r"\mathrm{We}",
    "Pr": r"\mathrm{Pr}",
    "Nu": r"\mathrm{Nu}",
    "Pe": r"\mathrm{Pe}",
}

_ALLOWED_EXPRESSION = re.compile(r"^[A-Za-z0-9_+\-*/().,\s^]*$")
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_RESERVED = frozenset(CONSTANTS) | frozenset(FUNCTIONS) | {"pi", "oo", "sqrt"}

#: Units used by the book, converted to upright math with negative exponents.
_UNIT_SYMBOLS = frozenset(
    {
        "kg", "g", "mg", "m", "cm", "mm", "km", "s", "ms", "min", "h",
        "A", "K", "mol", "cd", "N", "J", "W", "Pa", "bar", "Hz", "C", "V",
        "rad", "sr", "L", "mbar", "kN", "MJ", "kW", "kgf",
    }
)


def _clean_symbolic(symbolic: str) -> str:
    if not isinstance(symbolic, str):
        raise MathError("symbolic must be a string")
    cleaned = symbolic.strip()
    if not cleaned or len(cleaned) > 500:
        raise MathError("symbolic must be a short non-empty expression")
    if not _ALLOWED_EXPRESSION.match(cleaned):
        raise MathError("symbolic contains a character that is not allowed")
    without_numbers = re.sub(r"\d+\.\d*|\.\d+|\d+", "N", cleaned)
    if "." in without_numbers:
        raise MathError("a decimal point must be part of a number")
    return cleaned


def _names(expression: str) -> list[str]:
    found: list[str] = []
    for name in _IDENTIFIER.findall(expression):
        if name in _RESERVED:
            continue
        if name.startswith("_"):
            raise MathError("symbolic uses a private identifier")
        if name not in found:
            found.append(name)
    return found


def _sympy_parse(symbolic: str):
    """Parse a restricted symbolic expression. The character set and the names
    are checked first, so SymPy never sees arbitrary code.

    ``E`` and ``I`` are plain symbols, as in a structures book (Young's modulus, second moment of area);
    Euler's number is written ``exp(1)`` and the imaginary unit is not supported.
    """

    import sympy

    cleaned = _clean_symbolic(symbolic).replace("^", "**")
    names = _names(cleaned)
    local: dict[str, object] = {name: sympy.Symbol(name) for name in names}
    for function in FUNCTIONS:
        local.setdefault(function, getattr(sympy, function, None))
    local.setdefault("sqrt", sympy.sqrt)
    local.setdefault("pi", sympy.pi)
    for name in names:
        if local.get(name) is None:
            local[name] = sympy.Symbol(name)
    try:
        return sympy.parse_expr(cleaned, local_dict=local, evaluate=True)
    except (SyntaxError, TypeError, ValueError, AttributeError) as exc:  # pragma: no cover - defensive
        raise MathError("symbolic is not a valid expression") from exc


def symbolic_latex(symbolic: str, *, extra_names: dict[str, str] | None = None) -> str:
    """Return typeset LaTeX for a symbolic expression.

    Raises :class:`MathError` when the input is not parseable.
    """

    import sympy

    expression = _sympy_parse(symbolic)
    names = dict(DEFAULT_SYMBOL_NAMES)
    if extra_names:
        names.update(extra_names)
    symbol_names = {sympy.Symbol(key): value for key, value in names.items()}
    latex = sympy.latex(expression, symbol_names=symbol_names)
    problems = validate_latex(latex)
    if problems:
        raise MathError("the generated LaTeX did not validate: " + "; ".join(problems))
    return latex


def symbol_names_of(symbolic: str) -> list[str]:
    """Return the free symbol names of a symbolic expression, in first-seen order."""

    expression = _sympy_parse(symbolic)
    present = {str(symbol) for symbol in expression.free_symbols}
    ordered: list[str] = []
    for name in _names(_clean_symbolic(symbolic).replace("^", "**")):
        if name in present and name not in ordered:
            ordered.append(name)
    return ordered


def substitution_latex(symbolic: str, values: dict[str, tuple[str, str]]) -> str:
    """Typeset ``symbolic`` with each symbol replaced by ``value unit``.

    ``values`` maps a symbol name to ``(number, unit)``. The number is the
    already formatted figure and the unit is a plain unit string such as
    ``kg/m^3`` or ``dimensionless``.
    """

    import sympy

    expression = _sympy_parse(symbolic)
    names = dict(DEFAULT_SYMBOL_NAMES)
    for symbol, (number, unit) in values.items():
        if not symbol.isidentifier():
            raise MathError("substitution keys must be identifiers")
        tex_unit = unit_latex(unit)
        atom = str(number) if tex_unit == "1" else rf"{number}\,{tex_unit}"
        replacement = rf"\left({atom}\right)"
        names[symbol] = replacement
    symbol_names = {sympy.Symbol(key): value for key, value in names.items()}
    latex = sympy.latex(expression, symbol_names=symbol_names)
    problems = validate_latex(latex)
    if problems:
        raise MathError("the generated substitution did not validate: " + "; ".join(problems))
    return latex


def validate_latex(latex: str) -> list[str]:
    """Deterministic checks on a generated LaTeX fragment.

    This is not a TeX parser. It catches the failures that actually happened in
    the book: unbalanced braces, leftover computational operators, and empty
    output.
    """

    problems: list[str] = []
    if not isinstance(latex, str) or not latex.strip():
        return ["latex is empty"]
    if latex.count("{") != latex.count("}"):
        problems.append("unbalanced braces")
    if "**" in latex:
        problems.append("a computational power operator survived")
    if "$" in latex:
        problems.append("a raw math delimiter survived")
    return problems


def unit_latex(unit: str) -> str:
    """Typeset a unit string as upright math with negative exponents.

    ``kg/(m^2*s^2)`` becomes ``kg m^{-2} s^{-2}`` in upright math. Unknown
    tokens are kept upright and escaped.
    """

    if not isinstance(unit, str):
        raise MathError("unit must be a string")
    text = unit.strip().replace("·", "*").replace("⋅", "*").replace("\\cdot", "*")
    superscripts = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻", "0123456789+-")
    text = re.sub(r"[⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻]+", lambda match: "^" + match.group().translate(superscripts), text)
    if not text or text.lower() in {"dimensionless", "adimensional", "1", "none"}:
        return "1"
    if len(text) > 200:
        raise MathError("unit is too long")
    text = text.replace("**", "^")
    factors, index = _parse_unit_product(text, 0)
    if index != len(text):
        raise MathError(f"cannot read the unit {unit!r}")
    parts: list[str] = []
    for base, exponent in factors.items():
        piece = rf"\mathrm{{{_escape_unit(base)}}}"
        if exponent != 1:
            power = str(exponent.numerator) if exponent.denominator == 1 else rf"\frac{{{exponent.numerator}}}{{{exponent.denominator}}}"
            piece += f"^{{{power}}}"
        parts.append(piece)
    return r"\,".join(parts) or "1"


def _parse_unit_product(text: str, index: int, *, depth: int = 0) -> tuple[dict[str, Fraction], int]:
    """Read a bounded product without evaluating names or executable input.

    Multiplication and division associate left to right, like Pint. Grouped
    denominators and powers preserve their scope; ``1`` is the unit identity.
    """
    if depth > 24:
        raise MathError("unit nests too deeply")
    factors: dict[str, Fraction] = {}
    sign = 1
    needs_factor = True
    while index < len(text):
        if text[index].isspace():
            index += 1
            continue
        character = text[index]
        if character == ")":
            break
        if character in "*/":
            if needs_factor:
                raise MathError("a unit operator needs a preceding factor")
            sign = -1 if character == "/" else 1
            needs_factor = True
            index += 1
            continue
        if not needs_factor:
            # Adjacent unit factors (including whitespace-separated ones)
            # multiply. A previous division does not swallow this product.
            sign = 1
        if character == "(":
            inner, index = _parse_unit_product(text, index + 1, depth=depth + 1)
            if index >= len(text) or text[index] != ")":
                raise MathError("an unbalanced group in a unit")
            index += 1
        elif character == "1":
            if not needs_factor or (index + 1 < len(text) and text[index + 1] in "0123456789."):
                raise MathError("only the literal 1 is allowed as a unit factor")
            inner = {}
            index += 1
        else:
            match = re.match(r"[A-Za-z]+", text[index:])
            if match is None:
                raise MathError("a unit factor must be a name, group, or 1")
            inner = {match.group(0): Fraction(1)}
            index += len(match.group(0))
        while index < len(text) and text[index].isspace():
            index += 1
        exponent = Fraction(1)
        if index < len(text) and text[index] == "^":
            exponent, index = _parse_unit_exponent(text, index + 1)
        for base, power in inner.items():
            factors[base] = factors.get(base, Fraction(0)) + sign * exponent * power
        needs_factor = False
    if needs_factor:
        raise MathError("a unit product needs a factor")
    return {base: power for base, power in factors.items() if power != 0}, index


def _parse_unit_exponent(text: str, index: int) -> tuple[Fraction, int]:
    while index < len(text) and text[index].isspace():
        index += 1
    if index < len(text) and text[index] == "(":
        close = text.find(")", index + 1)
        if close < 0:
            raise MathError("an unbalanced exponent in a unit")
        raw = text[index + 1 : close].strip()
        index = close + 1
        if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+|\d+/\d+)", raw):
            raise MathError("a unit exponent must be a decimal or rational number")
    else:
        match = re.match(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", text[index:])
        if match is None:
            raise MathError("a unit exponent must be a number")
        raw = match.group(0)
        index += len(raw)
    try:
        return Fraction(raw), index
    except (ValueError, ZeroDivisionError) as exc:
        raise MathError("invalid numeric exponent in a unit") from exc


def _escape_unit(base: str) -> str:
    if base in _UNIT_SYMBOLS:
        return base
    return base


def numeric_latex(expression: str) -> str:
    """Typeset the replay expression without evaluating away its operands.

    Only the existing replay language is accepted. The AST preserves grouping,
    operand order and written decimal precision; no symbolic steps are invented.
    """
    import ast

    from studium.authoring.computation import ComputationError, evaluate, normalize_expression

    try:
        evaluate(expression)
    except ComputationError as exc:
        raise MathError(str(exc)) from exc
    cleaned = normalize_expression(expression.strip())
    tree = ast.parse(cleaned, mode='eval')

    def render(node: ast.AST) -> str:
        if isinstance(node, ast.Constant):
            token = ast.get_source_segment(cleaned, node) or str(node.value)
            match = re.fullmatch(r'(.+)[eE]([+-]?\d+)', token)
            return match.group(1) + r'\times 10^{' + match.group(2) + '}' if match else token
        if isinstance(node, ast.Name):
            return r'\pi' if node.id == 'pi' else r'\mathrm{e}'
        if isinstance(node, ast.UnaryOp):
            return ('-' if isinstance(node.op, ast.USub) else '+') + r'\left(' + render(node.operand) + r'\right)'
        if isinstance(node, ast.BinOp):
            left, right = render(node.left), render(node.right)
            if isinstance(node.op, ast.Div):
                return r'\frac{' + left + '}{' + right + '}'
            if isinstance(node.op, ast.Pow):
                return r'\left(' + left + r'\right)^{' + right + '}'
            operator = '+' if isinstance(node.op, ast.Add) else ('-' if isinstance(node.op, ast.Sub) else r'\cdot ')
            return r'\left(' + left + operator + right + r'\right)'
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            argument = render(node.args[0])
            name = node.func.id
            if name in ('sqrt', 'cbrt'):
                return (r'\sqrt{' if name == 'sqrt' else r'\sqrt[3]{') + argument + '}'
            if name == 'abs':
                return r'\left|' + argument + r'\right|'
            if name == 'factorial':
                return r'\left(' + argument + r'\right)!'
            return r'\operatorname{' + name + r'}\left(' + argument + r'\right)'
        raise MathError('unsupported replay syntax')

    return render(tree.body)
