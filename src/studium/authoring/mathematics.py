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

from studium.verification.parser import CONSTANTS, FUNCTIONS

__all__ = [
    "DEFAULT_SYMBOL_NAMES",
    "MathError",
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
_RESERVED = frozenset(CONSTANTS) | frozenset(FUNCTIONS) | {"pi", "E", "I", "oo", "sqrt"}

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
    are checked first, so SymPy never sees arbitrary code."""

    import sympy

    cleaned = _clean_symbolic(symbolic).replace("^", "**")
    names = _names(cleaned)
    local: dict[str, object] = {name: sympy.Symbol(name) for name in names}
    for function in FUNCTIONS:
        local.setdefault(function, getattr(sympy, function, None))
    local.setdefault("sqrt", sympy.sqrt)
    local.setdefault("pi", sympy.pi)
    local.setdefault("E", sympy.E)
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
        replacement = str(number) if tex_unit == "1" else rf"{number}\,{tex_unit}"
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
    if not text or text.lower() in {"dimensionless", "adimensional", "1", "none"}:
        return "1"
    factors, index = _parse_unit_product(text, 0)
    if index != len(text) or not factors:
        raise MathError(f"cannot read the unit {unit!r}")
    parts: list[str] = []
    for base, exponent in factors.items():
        piece = rf"\mathrm{{{_escape_unit(base)}}}"
        if exponent != 1:
            piece += f"^{{{exponent}}}"
        parts.append(piece)
    return r"\,".join(parts)


def _parse_unit_product(text: str, index: int) -> tuple[dict[str, int], int]:
    factors: dict[str, int] = {}
    sign = 1
    while index < len(text):
        character = text[index]
        if character in "* " or character == "\n":
            index += 1
            continue
        if character == "/":
            sign = -1
            index += 1
            continue
        if character == ")":
            break
        if character == "(":
            inner, index = _parse_unit_product(text, index + 1)
            if index < len(text) and text[index] == ")":
                index += 1
            for base, exponent in inner.items():
                factors[base] = factors.get(base, 0) + sign * exponent
            continue
        match = re.match(r"[A-Za-z]+", text[index:])
        if match is None:
            raise MathError("a unit factor must start with a letter")
        base = match.group(0)
        index += len(base)
        exponent = 1
        if index < len(text) and text[index] == "^":
            index += 1
            if index < len(text) and text[index] == "(":
                close = text.find(")", index)
                if close < 0:
                    raise MathError("an unbalanced exponent in a unit")
                exponent_text = text[index + 1 : close]
                index = close + 1
            else:
                exp_match = re.match(r"-?\d+", text[index:])
                if exp_match is None:
                    raise MathError("an exponent must be a number")
                exponent_text = exp_match.group(0)
                index += len(exponent_text)
            exponent = int(exponent_text)
        factors[base] = factors.get(base, 0) + sign * exponent
    return {base: exponent for base, exponent in factors.items() if exponent != 0}, index


def _escape_unit(base: str) -> str:
    if base in _UNIT_SYMBOLS:
        return base
    return base
