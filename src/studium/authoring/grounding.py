"""Grounding for the mathematical statements a draft paragraph carries.

A university explanation is not a transcript. It states equations the sources
did not spell out, derives results the reader is expected to follow, and works
small numeric examples. The audit must tell those apart instead of rejecting
every ``=`` that is not copied verbatim from an opened page.

Three groundings are recognised, and nothing else counts:

* ``source`` -- the statement is quoted by an excerpt the paragraph cites.
* ``derivation`` -- the statement is the final equation, a step, or the
  symbolic form of a stored derivation whose verification is not ``UNVERIFIED``
  and not ``FAILED``. The deduction is justified, not quoted.
* ``example`` -- the statement is an original numeric calculation the server
  evaluated again (``replayed``), or a number such a calculation produced.

A paragraph may also *declare* its mathematics with ``math`` entries. A
declaration names the kind and the stored ids it relies on, so an author can
state an equation in their own symbols without copying the source text and
without the auditor guessing. Every declaration is revalidated against the
stored artifacts; the server never accepts it on the model's word, and a
declaration never makes a formula verified or accepted.
"""

from __future__ import annotations

import json
import re
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from studium.authoring.excerpts import excerpts_by_id
from studium.authoring.latex_calculus import Definition, as_definition, check_with_premises
from studium.storage.records import COMPUTATIONS, DERIVATIONS, fold_by_id

MATH_KINDS = frozenset({"source", "derivation", "example"})

#: A derivation with one of these statuses carries a deterministic check that
#: passed. UNVERIFIED and FAILED justify nothing.
VERIFIED_DERIVATION_STATUSES = frozenset(
    {
        "COMPUTATION_REPRODUCED",
        "SYMBOLICALLY_VERIFIED",
        "DIMENSIONALLY_VERIFIED",
        "INDEPENDENTLY_VERIFIED",
        "ACADEMICALLY_REVIEWED",
    }
)

MAX_MATH_ENTRIES = 20
MAX_MATH_REFS = 20
_MAX_STATEMENT = 500
_MAX_REF = 128

_MATH_OPS = set("+-×·*/^()=")


def sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"[.!?]+", text) if part.strip()]


def formulas(sentence: str) -> list[str]:
    """Every ``=`` relation in one sentence, with the math tokens around it."""

    found: list[str] = []
    start = 0
    while True:
        index = sentence.find("=", start)
        if index < 0:
            return found
        left = _expand_math(sentence, index, -1)
        right = _expand_math(sentence, index + 1, 1)
        raw = " ".join(sentence[left:right].split())
        if _looks_like_formula(raw):
            found.append(raw)
        start = index + 1


def _looks_like_formula(raw: str) -> bool:
    compact = normalize_math(raw)
    if "=" not in compact:
        return False
    if re.fullmatch(r"[a-z][a-z0-9_]{0,40}=-?\d+(?:\.\d+)?", compact):
        return False
    return bool(re.search(r"[+\-*/]", compact))


def _expand_math(sentence: str, pos: int, direction: int) -> int:
    i = pos
    limit = len(sentence)
    while True:
        if direction < 0:
            while i > 0 and sentence[i - 1].isspace():
                i -= 1
            if i == 0:
                return 0
            if sentence[i - 1] in _MATH_OPS:
                i -= 1
                continue
            token_end = i
            while i > 0 and (sentence[i - 1].isalnum() or sentence[i - 1] == "_"):
                i -= 1
            token = sentence[i:token_end]
            if token and (_is_math_token(token) or token.isdigit()):
                toward = _nearest_nonspace(sentence, token_end, 1)
                if toward is not None and sentence[toward] in _MATH_OPS:
                    continue
            return token_end
        while i < limit and sentence[i].isspace():
            i += 1
        if i >= limit:
            return limit
        if sentence[i] in _MATH_OPS:
            i += 1
            continue
        token_start = i
        while i < limit and (sentence[i].isalnum() or sentence[i] == "_"):
            i += 1
        token = sentence[token_start:i]
        if token and (_is_math_token(token) or token.isdigit()):
            toward = _nearest_nonspace(sentence, token_start - 1, -1)
            if toward is not None and sentence[toward] in _MATH_OPS:
                continue
        return token_start


def _nearest_nonspace(sentence: str, pos: int, direction: int) -> int | None:
    i = pos
    while 0 <= i < len(sentence):
        if not sentence[i].isspace():
            return i
        i += direction
    return None


def _is_math_token(token: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z]{1,3}", token))


def normalize_math(text: str) -> str:
    """Collapse LaTeX and prose noise so two spellings of one relation compare.

    This is deliberately lossy: it removes math delimiters, thin spaces, groups,
    and whitespace, and maps the multiplication and minus glyphs. Symbolic
    equivalence (:func:`equivalent_math`) catches the cases this cannot.
    """

    cleaned = text.casefold()
    cleaned = (
        cleaned.replace("×", "*")
        .replace("·", "*")
        .replace("⋅", "*")
        .replace("∗", "*")  # noqa: RUF001 - the asterisk operator is real input, not a typo
        .replace("−", "-")
        .replace("–", "-")
        .replace("—", "-")
    )
    cleaned = cleaned.replace(r"\times", "*").replace(r"\cdot", "*").replace(r"\left", "").replace(r"\right", "")
    cleaned = re.sub(r"\\[,!;:]", "", cleaned)
    cleaned = re.sub(r"\\[()\[\]]", "", cleaned)
    cleaned = re.sub(r"\\(?:mathrm|text|operatorname)\{([^{}]*)\}", r"\1", cleaned)
    cleaned = cleaned.replace("$", "").replace("{", "").replace("}", "")
    return "".join(cleaned.split())


def _ascii_form(text: str) -> str:
    """The normalized ASCII spelling of a relation, for exact comparison."""

    return normalize_math(_latex_to_ascii(text))


def _canon(text: str) -> str:
    """ASCII spelling with subscripts folded, so ``V_1`` compares with ``V1``."""

    return _ascii_form(text).replace("_", "")


def contains_formula(statement: str, body: str) -> bool:
    """True when ``body`` states ``statement`` up to normalization."""

    needle = normalize_math(statement)
    if not needle or "=" not in needle:
        return False
    if needle in normalize_math(body):
        return True
    folded = _canon(statement)
    return bool(folded) and folded in _canon(body)


@lru_cache(maxsize=8192)
def equivalent_math(left: str, right: str) -> bool:
    """Compare algebraic relations on their common defined domain.

    Accept identical relations, rearrangements and nonzero constant
    multiples. This is not a proof of physical validity.
    """
    if normalize_math(left) == normalize_math(right) and "=" in normalize_math(left):
        return True

    if _canon(left) == _canon(right) and "=" in _canon(left):
        return True

    first = _relation(left)
    second = _relation(right)

    if first is None or second is None:
        return False

    return _same_up_to_constant(cast(Any, first), cast(Any, second))


#: An expression with more operations than this is not compared symbolically.
_MAX_OPS = 120


def _same_up_to_constant(first: Any, second: Any) -> bool:
    """Whether two residuals (``lhs - rhs``) are equal or differ by a nonzero constant factor.

    Exact and bounded: the same free symbols, ``expand`` and ``cancel`` only
    (no ``simplify``, whose cost is unbounded). Transcendental functions are
    treated as atoms, so an identity that needs a trigonometric or logarithmic
    rewrite is not recognised; that is a missed match, never a false one.
    """

    import sympy

    if first.free_symbols != second.free_symbols:
        return False
    if sympy.count_ops(first) > _MAX_OPS or sympy.count_ops(second) > _MAX_OPS:
        return False
    try:
        first_num, _ = sympy.fraction(sympy.together(first))
        second_num, _ = sympy.fraction(sympy.together(second))
        if sympy.expand(first_num - second_num) == 0 or sympy.expand(first_num + second_num) == 0:
            return True
        if second_num == 0 or first_num == 0:
            return False
        ratio = sympy.cancel(first_num / second_num)
        return bool(ratio.is_number and ratio.is_nonzero is True)
    except (TypeError, ValueError, ZeroDivisionError, AttributeError, RecursionError):
        return False


@lru_cache(maxsize=4096)
def _relation(equation: str):
    """Parse a restricted algebraic equality without evaluating Python code."""
    import ast

    import sympy

    text = _sympy_text(equation)
    if text is None or len(text) > 400 or text.count("=") != 1:
        return None

    left, right = text.split("=", 1)

    def parse(side: str):
        tree = ast.parse(side.strip().replace("^", "**"), mode="eval")

        if sum(1 for _ in ast.walk(tree)) > 64:
            raise ValueError("expression too complex")

        def convert(node, depth: int = 0):
            if depth > 16:
                raise ValueError("expression too deep")

            if isinstance(node, ast.Expression):
                return convert(node.body, depth + 1)

            if isinstance(node, ast.Constant):
                if type(node.value) not in (int, float):
                    raise ValueError("invalid constant")
                if len(str(node.value)) > 20:
                    raise ValueError("number too large")
                return sympy.Rational(str(node.value))

            if isinstance(node, ast.Name):
                if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", node.id):
                    raise ValueError("invalid symbol")
                if node.id == "pi":
                    return sympy.pi
                return sympy.Symbol(node.id)

            if isinstance(node, ast.Call):
                if (
                    not isinstance(node.func, ast.Name)
                    or node.func.id not in _FUNCTION_NAMES
                    or len(node.args) != 1
                    or node.keywords
                ):
                    raise ValueError("unsupported function")
                return _sympy_functions()[node.func.id](convert(node.args[0], depth + 1))

            if isinstance(node, ast.UnaryOp):
                value = convert(node.operand, depth + 1)

                if isinstance(node.op, ast.USub):
                    return -value
                if isinstance(node.op, ast.UAdd):
                    return value

                raise ValueError("invalid unary operator")

            if isinstance(node, ast.BinOp):
                a = convert(node.left, depth + 1)
                b = convert(node.right, depth + 1)

                if isinstance(node.op, ast.Add):
                    return a + b
                if isinstance(node.op, ast.Sub):
                    return a - b
                if isinstance(node.op, ast.Mult):
                    return a * b
                if isinstance(node.op, ast.Div):
                    return a / b
                if isinstance(node.op, ast.Pow):
                    if a == sympy.Symbol("e"):
                        # e^{x} in a physics text is the exponential.
                        return sympy.exp(b)
                    if b.is_Rational is not True or abs(b.p) > 8 or b.q > 4:
                        raise ValueError("unsupported exponent")
                    return a**b

                raise ValueError("invalid binary operator")

            raise ValueError("unsupported syntax")

        return convert(tree)

    try:
        lhs = parse(left)
        rhs = parse(right)
        return cast(Any, lhs) - cast(Any, rhs)
    except (SyntaxError, ValueError, TypeError, ZeroDivisionError, OverflowError):
        return None


def _sympy_functions() -> dict[str, Any]:
    import sympy

    return {
        "sin": sympy.sin,
        "cos": sympy.cos,
        "tan": sympy.tan,
        "exp": sympy.exp,
        "ln": sympy.log,
        "log": sympy.log,
        "sqrt": sympy.sqrt,
        "sinh": sympy.sinh,
        "cosh": sympy.cosh,
        "tanh": sympy.tanh,
    }


_FUNCTION_NAMES = frozenset({"sin", "cos", "tan", "exp", "ln", "log", "sqrt", "sinh", "cosh", "tanh"})
#: Notation the scalar relation parser must not read: vector and tensor operators,
#: calculus, sums and norms. Such a relation stays not machine-checkable.
_UNREADABLE = re.compile(
    r"\\(?:nabla|int|iint|iiint|oint|oiint|sum|prod|lim|partial|mathcal|operatorname\{div|otimes|wedge)(?![A-Za-z])|\|"
)
#: A differential or derivative (``dx``, ``du/dy``, ``d\\mathbf{p}``, ``d^{2}u``, ``\\mathrm{d}x``) is not a
#: product ``d*x``; reading it as one makes ``du/dy`` equal ``u/y``. Such relations stay not machine-checkable.
_DIFFERENTIAL = re.compile(
    r"\\mathrm\{d\}|(?<![A-Za-z0-9_\\])d(?:\^\{?\d\}?)?\s*(?=\\[A-Za-z]|[A-Za-z](?![A-Za-z]{2}))(?!_)"
)
_VECTOR = re.compile(r"\\(?:mathbf|boldsymbol|vec|bm)\s*\{")
_VECTOR_PRODUCT = re.compile(r"\\(?:times|cdot|wedge|otimes)(?![A-Za-z])")


def _sympy_text(equation: str) -> str | None:
    """A Python-syntax spelling of a scalar LaTeX relation, or None when it uses notation SymPy must not guess.

    Vectors are read as distinct symbols only in scalar multiples; a vector or
    tensor product, a calculus operator, a sum or a norm makes the relation not
    machine-checkable instead of silently wrong.
    """

    if _UNREADABLE.search(equation) or _DIFFERENTIAL.search(equation):
        return None
    if _VECTOR.search(equation) and _VECTOR_PRODUCT.search(equation):
        return None
    if r"\begin" in equation:
        return None
    text = re.sub(r"\\[,;:!]|~", " ", equation)
    # An accent or a Delta applies to the next symbol: \dot m, \dot\gamma, \Delta p are one quantity each.
    text = re.sub(r"\\(dot|ddot|bar|hat|tilde)\s*(\\[A-Za-z]+|[A-Za-z])(?![A-Za-z])", r"\\\1{\2}", text)
    text = re.sub(r"\\Delta\s*(\\[A-Za-z]+|[A-Za-z])((?:_\{[^{}]*\}|_\\?[A-Za-z0-9])?)", r"\\Deltaof{\1\2}", text)
    text = re.sub(r"\\[td]frac(?![A-Za-z])", r"\\frac", text)
    text = re.sub(r"\\frac\s*(\d)\s*(\d)", r"((\1)/(\2))", text)
    text = _replace_command(text, "frac", 2, "(({0})/({1}))")
    text = _replace_sqrt(text)
    for command in ("mathbf", "boldsymbol", "vec", "bm"):
        text = _replace_command(text, command, 1, " {0}_vec ")
    for command in ("mathrm", "text", "operatorname", "mathit"):
        text = _replace_command(text, command, 1, " {0} ")
    text = _replace_command(text, "Deltaof", 1, " Delta_{0} ")
    text = re.sub(r"\\(dot|ddot)\{\s*(\\?[A-Za-z]+)\s*\}", r"\2_\1", text)
    # Every command starts a new token: \\omega t, A\\cos\\omega t.
    text = re.sub(r"\\(?=[A-Za-z])", " \\\\", text)
    text = _latex_to_ascii(text)
    # A bracket is a grouping only where it cannot be an index (never right after a name).
    if re.search(r"[A-Za-z0-9_]\s*\[", text):
        return None
    text = text.replace("[", "(").replace("]", ")")
    text = re.sub(r"\s+_", "_", text)
    text = re.sub(r"_\s+", "_", text)
    text = re.sub(r"\^\s+", "^", text)
    text = re.sub(r"_\(([A-Za-z0-9]+)\)", r"_\1", text)
    # Function-value notation u(0), x(t), p(z): one symbol, not a product or an unknown function.
    text = re.sub(
        r"\b(?!(?:" + "|".join(_FUNCTION_NAMES) + r")\()([A-Za-z][A-Za-z0-9_]*)\(\s*([A-Za-z0-9_.]+)\s*\)",
        r"\1_at_\2",
        text,
    )
    text = _function_arguments(text)
    text = _implicit_products(text)
    if "\\" in text:
        return None
    return text


def _braced(text: str, start: int) -> tuple[str, int] | None:
    """The content of the balanced ``{...}`` starting at ``start`` (spaces skipped), and the index after it."""

    index = start
    while index < len(text) and text[index].isspace():
        index += 1
    if index >= len(text) or text[index] != "{":
        return None
    depth = 0
    for position in range(index, len(text)):
        if text[position] == "{":
            depth += 1
        elif text[position] == "}":
            depth -= 1
            if depth == 0:
                return text[index + 1 : position], position + 1
    return None


def _replace_command(text: str, name: str, arguments: int, template: str) -> str:
    pattern = re.compile(r"\\" + name + r"(?![A-Za-z])")
    for _ in range(50):
        match = pattern.search(text)
        if match is None:
            return text
        position = match.end()
        values: list[str] = []
        for _argument in range(arguments):
            found = _braced(text, position)
            if found is None:
                return text
            values.append(found[0])
            position = found[1]
        text = text[: match.start()] + template.format(*values) + text[position:]
    return text


def _replace_sqrt(text: str) -> str:
    for _ in range(50):
        match = re.search(r"\\sqrt(?![A-Za-z])\s*(\[([^\]]*)\])?", text)
        if match is None:
            return text
        found = _braced(text, match.end())
        if found is None:
            return text
        index = match.group(2)
        body = f"(({found[0]})**(1/({index})))" if index else f"sqrt({found[0]})"
        text = text[: match.start()] + body + text[found[1] :]
    return text


def _function_arguments(text: str) -> str:
    """``sin theta`` -> ``sin(theta)``; an argument runs to the next top-level + - = or the end."""

    out: list[str] = []
    index = 0
    pattern = re.compile(r"\b(" + "|".join(sorted(_FUNCTION_NAMES, key=len, reverse=True)) + r")\b\s*")
    while index < len(text):
        match = pattern.match(text, index)
        if match is None or (index > 0 and (text[index - 1].isalnum() or text[index - 1] == "_")):
            out.append(text[index])
            index += 1
            continue
        out.append(match.group(1))
        position = match.end()
        if position < len(text) and text[position] == "(":
            index = position
            continue
        end = position
        depth = 0
        while end < len(text):
            character = text[end]
            if character == "(":
                depth += 1
            elif character == ")":
                if depth == 0:
                    break
                depth -= 1
            elif depth == 0 and character in "+-=" and end > position:
                break
            end += 1
        out.append("(" + text[position:end].strip() + ")")
        index = end
    return "".join(out)


def _implicit_products(text: str) -> str:
    """Make juxtaposed factors explicit: ``2 g h`` -> ``2*g*h``, ``)(`` -> ``)*(``, ``2(`` -> ``2*(``."""

    text = re.sub(r"(?<=[A-Za-z0-9_)])\s+(?=[A-Za-z0-9_(])", "*", text.strip())
    text = re.sub(r"\)\s*\(", ")*(", text)
    text = re.sub(r"(?<=\d)(?=[A-Za-z(])", "*", text)
    text = re.sub(r"\)(?=[A-Za-z0-9])", ")*", text)
    text = re.sub(r"(?<=[A-Za-z0-9_])\(", "*(", text)
    # A function name keeps its call parenthesis.
    return re.sub(r"\b(" + "|".join(_FUNCTION_NAMES) + r")\*\(", r"\1(", text)


_GREEK = {
    "alpha": "alpha",
    "beta": "beta",
    "gamma": "gamma",
    "Gamma": "Gamma",
    "delta": "delta",
    "Delta": "Delta",
    "epsilon": "epsilon",
    "varepsilon": "varepsilon",
    "zeta": "zeta",
    "eta": "eta",
    "theta": "theta",
    "Theta": "Theta",
    "iota": "iota",
    "kappa": "kappa",
    "lambda": "lambda",
    "Lambda": "Lambda",
    "mu": "mu",
    "nu": "nu",
    "xi": "xi",
    "pi": "pi",
    "Pi": "Pi",
    "rho": "rho",
    "sigma": "sigma",
    "Sigma": "Sigma",
    "tau": "tau",
    "phi": "phi",
    "varphi": "phi",
    "Phi": "Phi",
    "chi": "chi",
    "psi": "psi",
    "Psi": "Psi",
    "omega": "omega",
    "Omega": "Omega",
}


_GLYPHS = {0x00D7: "*", 0x00B7: "*", 0x22C5: "*", 0x2212: "-", 0x2013: "-", 0x00F7: "/"}


def _latex_to_ascii(text: str) -> str:
    """A small ASCII spelling for a LaTeX relation, good enough for SymPy.

    The Greek names and ``\\frac`` cover the notation this book actually uses.
    Unknown commands are left in place, and then SymPy fails cleanly.
    """

    cleaned = text.replace(r"\left", "").replace(r"\right", "")
    cleaned = cleaned.translate(_GLYPHS)
    cleaned = cleaned.replace(r"\,", "").replace(r"\!", "").replace(r"\;", "").replace(r"\:", "")
    cleaned = re.sub(r"\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}", r"((\1)/(\2))", cleaned)
    # Accents become a suffix, so \dot{m} compares with a plain "mdot".
    cleaned = re.sub(r"\\(dot|ddot|vec|bar|hat|tilde|overline)\s*\{([^{}]*)\}", r"\2\1", cleaned)
    # Subscripts lose their braces, so \dot{m}_{in} compares with "mdot_in".
    cleaned = re.sub(r"_\{([^{}]*)\}", r"_\1", cleaned)
    cleaned = cleaned.replace(r"\cdot", "*").replace(r"\times", "*")
    cleaned = cleaned.replace(r"\partial", "d")
    for name in sorted(_GREEK, key=len, reverse=True):
        cleaned = cleaned.replace("\\" + name, _GREEK[name] + " ")
    cleaned = re.sub(r"\\([A-Za-z]+)", r"\1", cleaned)
    cleaned = cleaned.replace("^", "**").replace("{", "(").replace("}", ")")
    cleaned = re.sub(r"\\[()\[\]]", "", cleaned)
    return cleaned


def record_excerpt_texts(record: dict[str, object], stored: dict[str, dict[str, object]]) -> list[str]:
    """The bodies of the excerpts a stored record cites, in stored order."""
    raw_value = record.get("excerpts")
    raw = raw_value if isinstance(raw_value, list) else []
    bodies: list[str] = []
    for excerpt_id in raw:
        excerpt = stored.get(excerpt_id) if isinstance(excerpt_id, str) else None
        body = excerpt.get("text") if isinstance(excerpt, dict) else None
        if isinstance(body, str) and body.strip():
            bodies.append(body)
    return bodies


def replayed_computations(root: Path) -> list[dict[str, object]]:
    return [
        record
        for record in fold_by_id(root / COMPUTATIONS)
        if record.get("status") == "replayed" and record.get("correct") is True
    ]


def verified_derivations(root: Path, section: object) -> list[dict[str, object]]:
    """Live derivations of one section whose deterministic check passed."""

    if not isinstance(section, str):
        return []
    found: list[dict[str, object]] = []
    for record in fold_by_id(root / DERIVATIONS):
        if record.get("section") != section or record.get("deleted") is True:
            continue
        verification = record.get("verification")
        status = str(verification.get("status")) if isinstance(verification, dict) else "UNVERIFIED"
        if status in VERIFIED_DERIVATION_STATUSES:
            found.append(record)
    return found


def derivation_statements(record: dict[str, object]) -> list[str]:
    """Every readable mathematical line a derivation can ground a formula with."""

    lines: list[str] = []
    equation = record.get("equation")
    if isinstance(equation, str) and equation.strip():
        lines.append(equation.strip())
    steps = record.get("steps_latex")
    if isinstance(steps, list):
        lines.extend(item.strip() for item in steps if isinstance(item, str) and item.strip())
    symbolic = record.get("symbolic")
    if isinstance(symbolic, str) and symbolic.strip():
        lines.append(symbolic.strip())
    return lines


def declared_math(record: dict[str, object]) -> list[dict[str, object]]:
    raw = record.get("math")
    if not isinstance(raw, list):
        return []
    return [entry for entry in raw if isinstance(entry, dict)]


def parse_math(value: object) -> tuple[list[dict[str, object]] | None, dict[str, object] | None]:
    """Validate and clean the ``math`` declarations of a paragraph."""

    if value is None:
        return [], None
    if not isinstance(value, list):
        return None, _error("mcp.invalid_input", "math must be a list of declarations")
    if len(value) > MAX_MATH_ENTRIES:
        return None, _error("mcp.invalid_input", f"math may carry at most {MAX_MATH_ENTRIES} declarations")
    cleaned: list[dict[str, object]] = []
    for entry in value:
        if not isinstance(entry, dict):
            return None, _error("mcp.invalid_input", "each math declaration must be an object")
        statement = entry.get("statement")
        if not isinstance(statement, str) or not statement.strip() or len(statement) > _MAX_STATEMENT:
            return None, _error("mcp.invalid_input", "each math declaration needs a short statement")
        kind = entry.get("kind")
        if kind not in MATH_KINDS:
            return None, _error("mcp.invalid_input", "math kind must be source, derivation, or example")
        refs_value = entry.get("refs")
        if not isinstance(refs_value, list) or not refs_value:
            return None, _error("mcp.invalid_input", "each math declaration needs at least one ref")
        refs: list[str] = []
        for item in refs_value:
            if not isinstance(item, str) or not item.strip() or len(item.strip()) > _MAX_REF:
                return None, _error("mcp.invalid_input", "math refs must be short stored ids")
            identifier = item.strip()
            if identifier not in refs:
                refs.append(identifier)
        if len(refs) > MAX_MATH_REFS:
            return None, _error("mcp.invalid_input", f"math declarations may cite at most {MAX_MATH_REFS} refs")
        cleaned.append({"statement": statement.strip(), "kind": kind, "refs": refs})
    return cleaned, None


def validate_math(
    root: Path,
    entries: list[dict[str, object]],
    *,
    section: str,
    excerpt_ids: list[str],
) -> dict[str, object] | None:
    """Revalidate every declaration against the artifacts the book already holds.

    A ``source`` statement must be quoted by one of the paragraph's own cited
    excerpts. A ``derivation`` statement must be an equation, step, or symbolic
    form of a stored, verified derivation in the same section. An ``example``
    statement must rest on computations the server replayed.
    """

    stored = excerpts_by_id(root)
    cited = [item for item in excerpt_ids if isinstance(item, str)]
    for entry in entries:
        kind = str(entry.get("kind"))
        statement = str(entry.get("statement"))
        raw_refs = entry.get("refs")
        refs = [item for item in raw_refs if isinstance(item, str)] if isinstance(raw_refs, list) else []
        if kind == "source":
            unknown = [item for item in refs if item not in cited]
            if unknown:
                return _error(
                    "paragraph.math_ungrounded",
                    "a source declaration may only cite the paragraph's own excerpts",
                )
            bodies = [stored[item]["text"] for item in refs if isinstance(stored.get(item), dict)]
            bodies = [body for body in bodies if isinstance(body, str)]
            if not any(contains_formula(statement, body) for body in bodies):
                return _error(
                    "paragraph.math_ungrounded",
                    "a source declaration must be quoted by a cited excerpt: " + statement,
                )
        elif kind == "derivation":
            for identifier in refs:
                derivation = _derivation(root, identifier)
                if derivation is None:
                    return _error("paragraph.math_ungrounded", f"no stored derivation {identifier}")
                if derivation.get("section") != section:
                    return _error(
                        "paragraph.math_ungrounded",
                        f"derivation {identifier} belongs to another section",
                    )
                verification = derivation.get("verification")
                status = str(verification.get("status")) if isinstance(verification, dict) else "UNVERIFIED"
                if status not in VERIFIED_DERIVATION_STATUSES:
                    return _error(
                        "paragraph.math_ungrounded",
                        f"derivation {identifier} carries no passing deterministic check",
                    )
            statements = [
                line
                for identifier in refs
                for line in derivation_statements(_derivation(root, identifier) or {})
            ]
            if not any(contains_formula(statement, line) or equivalent_math(statement, line) for line in statements):
                return _error(
                    "paragraph.math_ungrounded",
                    "a derivation declaration must state the derivation: " + statement,
                )
        elif kind == "example":
            for identifier in refs:
                computation = _computation(root, identifier)
                if computation is None:
                    return _error("paragraph.math_ungrounded", f"no stored computation {identifier}")
                if computation.get("status") != "replayed" or computation.get("correct") is not True:
                    return _error(
                        "paragraph.math_ungrounded",
                        f"computation {identifier} was not replayed",
                    )
                allowed = _computation_numbers(computation)
                numbers = {_canon_number(item) for item in re.findall(r"-?\d+(?:\.\d+)?", statement)}
                if not numbers <= allowed:
                    return _error(
                        "paragraph.math_ungrounded",
                        f"an example declaration states a number {identifier} did not produce: " + statement,
                    )
    return None


#: Evidence statuses of a prose equation, strongest first. A status names the
#: evidence the project holds for the exact statement; none of them is human
#: approval, and source support is not a proof.
VERIFIED_STATUSES = ("symbolically_verified", "dimensionally_verified", "numerically_reproduced")
EQUATION_STATUSES = (
    "symbolically_verified",
    "dimensionally_verified",
    "numerically_reproduced",
    "source_supported",
    "follows_from_stated_premises",
    "derived_steps_unchecked",
    "numerically_ambiguous",
    "not_machine_checkable",
    "unsupported",
    "contradicted",
    "verification_failed",
)
#: Relations that are not claims to verify.
NON_CLAIM_STATUSES = ("definition", "approximation", "value_or_condition")
FORMULA_STATUSES = EQUATION_STATUSES + NON_CLAIM_STATUSES
#: The evidence audit blocks on these: a readable claim nothing supports, a
#: relation the numbers contradict, or one a stored check failed.
BLOCKING_STATUSES = frozenset({"unsupported", "contradicted", "verification_failed"})
#: Statuses whose equation still needs a person to look at it.
HUMAN_REVIEW_STATUSES = frozenset(
    {
        "not_machine_checkable",
        "unsupported",
        "derived_steps_unchecked",
        "numerically_ambiguous",
        "source_supported",
        "follows_from_stated_premises",
    }
)
_DERIVATION_EVIDENCE = {
    "SYMBOLICALLY_VERIFIED": "symbolically_verified",
    "INDEPENDENTLY_VERIFIED": "symbolically_verified",
    "ACADEMICALLY_REVIEWED": "symbolically_verified",
    "DIMENSIONALLY_VERIFIED": "dimensionally_verified",
    "COMPUTATION_REPRODUCED": "numerically_reproduced",
}
_RANK = {status: index for index, status in enumerate(EQUATION_STATUSES)}
#: Kept for callers of the earlier API: the statuses that count as grounded.
GROUNDED_STATUSES = frozenset({*VERIFIED_STATUSES, "source_supported"})

_ENVIRONMENTS = r"(?:equation|align|gather|multline|eqnarray|displaymath)\*?"
_SPAN = re.compile(
    r"\\begin\{(" + _ENVIRONMENTS + r")\}(.+?)\\end\{\1\}|\$\$(.+?)\$\$|\\\[(.+?)\\\]|\\\((.+?)\\\)|\$([^$]+)\$",
    re.S,
)
#: Math spans shown as display equations: environments, ``$$`` and ``\\[``.
_DISPLAY = re.compile(r"\\begin\{(" + _ENVIRONMENTS + r")\}(.+?)\\end\{\1\}|\$\$(.+?)\$\$|\\\[(.+?)\\\]", re.S)
_RELATION_OPS = re.compile(
    r"\\(?:approx|simeq|equiv|geq?|leq?|neq?|gg|ll|propto|sim)(?![A-Za-z])|:=|(?<![<>!\\])[<>]=?|(?<![<>!\\:])="
)
_OP_KINDS = {
    "=": "claim",
    "\\approx": "approximation",
    "\\simeq": "approximation",
    "\\equiv": "definition",
    ":=": "definition",
}


def _kind_of(operator: str) -> str:
    return _OP_KINDS.get(operator, "condition")
_TRAILING = " ,;.:"


def math_statements(text: str) -> list[tuple[str, str]]:
    """See :func:`_math_statements`; the result is memoized per text and returned as a new list."""

    return list(_math_statements(text))


@lru_cache(maxsize=4096)
def _math_statements(text: str) -> tuple[tuple[str, str], ...]:
    """Every complete relation in a passage, as ``(kind, "lhs op rhs")``.

    Math spans (``$..$``, ``$$..$$``, ``\\(..\\)``, ``\\[..\\]``) are split at their
    top-level relation operators, so a chain ``a = b = c`` gives ``a = b`` and
    ``b = c``. Outside math spans the plain-text detector is kept, but only for
    relations with both sides present. ``kind`` is ``claim`` (``=``),
    ``definition`` (``\\equiv``, ``:=``) or ``approximation`` (``\\approx``).
    No fragment such as ``= -p`` is ever returned.
    """

    found: list[tuple[str, str]] = []
    outside: list[str] = []
    last = 0
    for match in _SPAN.finditer(text):
        outside.append(text[last : match.start()])
        last = match.end()
        body = _span_body(match)
        for piece in _top_level_pieces(body):
            parts, operators = _split_relations(piece)
            for index, operator in enumerate(operators):
                left = parts[index].strip().strip(_TRAILING).strip()
                right = parts[index + 1].strip().strip(_TRAILING).strip()
                if _complete_side(left, -1) and _complete_side(right, 1) and not _elided(left) and not _elided(right):
                    found.append((_kind_of(operator), f"{left} {operator} {right}"))
    outside.append(text[last:])
    for sentence in sentences(" ".join(outside)):
        for formula in formulas(sentence):
            # Plain-text relations only: LaTeX outside a math span is not read in pieces.
            if "\\" in formula:
                continue
            # A chain ``a = b = c`` states ``a = b`` and ``b = c``, as it does inside a math span.
            sides = [side.strip() for side in re.split(r"(?<![<>!:=])=(?!=)", formula)]
            if len(sides) > 2 and all(sides):
                links = [f"{sides[index]} = {sides[index + 1]}" for index in range(len(sides) - 1)]
            else:
                links = [formula]
            for link in links:
                left, _sign, right = link.partition("=")
                if _complete_side(left, -1) and _complete_side(right, 1):
                    found.append(("claim", link))
    return tuple(found)


def _span_body(match: re.Match[str]) -> str:
    """The math inside a span; an environment drops its labels, tags and alignment marks."""

    groups = match.groups()
    if groups[0] is not None and groups[1] is not None:
        body = re.sub(r"\\(?:label|tag|nonumber|notag)\b(?:\{[^{}]*\})?", " ", groups[1])
        return body
    return next(group for group in groups[2:] if group is not None)


#: ``\\,`` and ``\\;`` are thin spaces, not separators: a comma or colon preceded by a backslash never splits.
_SEPARATORS = re.compile(
    r"\\q?quad\b|\\\\|(?<!\\);|(?<!\\),(?=\s|\\)|(?<!\\):(?=\s|\\q?quad\b)|\\(?:text|mbox|mathrm)\{[^{}]*\s[^{}]*\}"
)


def _top_level_pieces(body: str) -> list[str]:
    """Split a math span at top-level separators (``\\quad``, ``,\\ ``, ``;``, ``\\text{ y }``, ``\\\\``).

    Alignment marks ``&`` are dropped; nothing inside braces, parentheses or a
    nested environment (a matrix, cases) is split.
    """

    parts, _operators = _split_top(body.replace("&", " ") if "\\begin" not in body else _drop_alignment(body), _SEPARATORS)
    return [piece for piece in parts if piece.strip()]


def _split_relations(body: str) -> tuple[list[str], list[str]]:
    return _split_top(body, _RELATION_OPS)


_BEGIN = re.compile(r"\\begin\{[^{}]*\}")
_END = re.compile(r"\\end\{[^{}]*\}")


def _split_top(body: str, pattern: re.Pattern[str]) -> tuple[list[str], list[str]]:
    """Split ``body`` where ``pattern`` matches at depth zero; return the parts and the matched tokens."""

    parts: list[str] = []
    tokens: list[str] = []
    depth = 0
    last = 0
    index = 0
    while index < len(body):
        begin = _BEGIN.match(body, index)
        if begin:
            depth += 1
            index = begin.end()
            continue
        end = _END.match(body, index)
        if end:
            depth -= 1
            index = end.end()
            continue
        character = body[index]
        if character == "\\" and index + 1 < len(body) and body[index + 1] in "{}":
            index += 2
            continue
        if character in "{(":
            depth += 1
        elif character in "})":
            depth -= 1
        elif depth == 0:
            match = pattern.match(body, index)
            if match:
                parts.append(body[last:index])
                tokens.append(match.group(0))
                last = index = match.end()
                continue
        index += 1
    parts.append(body[last:])
    return parts, tokens


def _drop_alignment(body: str) -> str:
    """Drop ``&`` at depth zero only; a nested matrix keeps its column marks."""

    kept: list[str] = []
    depth = 0
    index = 0
    while index < len(body):
        begin = _BEGIN.match(body, index)
        end = _END.match(body, index)
        if begin or end:
            token = (begin or end).group(0)  # type: ignore[union-attr]
            depth += 1 if begin else -1
            kept.append(token)
            index += len(token)
            continue
        character = body[index]
        kept.append(" " if character == "&" and depth == 0 else character)
        index += 1
    return "".join(kept)


def _complete_side(side: str, direction: int) -> bool:
    """Both ends of a side are whole: no dangling operator on either end."""

    compact = "".join(side.split())
    if not compact:
        return False
    if compact[0] in "+*/^×·)=" or compact[-1] in "+-*/^×·(=":
        return False
    return not (direction < 0 and compact.endswith("\\"))


def _elided(side: str) -> bool:
    return any(mark in side for mark in ("\\ldots", "\\cdots", "\\dots", "..."))


_ATOM = re.compile(r"[A-Za-z][A-Za-z0-9_]*'*|-?\d+(?:\.\d+)?")


def _condition(statement: str) -> bool:
    """A value or condition (``x = 0``, ``r = R``, ``U_0 = 50``), not a formula to ground.

    Numbers in it are checked by the number rules of the audit, not here.
    """

    left, _sign, right = statement.partition("=")
    if _DIFFERENTIAL.search(statement):
        return False
    sides = []
    for side in (left, right):
        number = _arithmetic_text(side)
        text = number if number is not None else (_sympy_text(side) or _latex_to_ascii(side)).strip()
        sides.append(text.strip("() "))
    return all(_ATOM.fullmatch(side) for side in sides)


class GroundingContext:
    """What a relation may be grounded by, read once for many relations."""

    def __init__(self, root: Path) -> None:
        from studium.storage.records import VERIFICATIONS

        self.root = root
        self.excerpts = excerpts_by_id(root)
        self.computations = replayed_computations(root)
        self._units: Any = None
        self.derivation_records = [record for record in fold_by_id(root / DERIVATIONS) if record.get("deleted") is not True]
        self.verifications = [
            record
            for record in fold_by_id(root / VERIFICATIONS)
            if record.get("check") in {"equation", "equivalence"} and isinstance(record.get("inputs"), dict)
        ]

    def derivations(self, section: object) -> list[dict[str, object]]:
        return [record for record in self.derivation_records if record.get("section") == section]

    def dimension_probe(self, statement: str) -> dict[str, object]:
        """Dimensional plausibility of a relation under the registered notation units (not a status)."""

        from studium.authoring.equation_dimensions import EquationUnits

        if self._units is None:
            self._units = EquationUnits(self.root)
        probe: dict[str, object] = self._units.probe(statement)
        return probe


def formula_statuses(
    root: Path, record: dict[str, object], context: GroundingContext | None = None
) -> list[tuple[str, str]]:
    """Each complete relation the record states, with its evidence status."""

    return [(str(item["statement"]), str(item["status"])) for item in equation_evidence(root, record, context)]


def equation_evidence(
    root: Path, record: dict[str, object], context: GroundingContext | None = None
) -> list[dict[str, object]]:
    """Each complete relation the record states, as written, with its status and evidence ids.

    The statement is kept exactly as the author wrote it. ``important`` marks
    display equations. ``human_review`` says whether a person still has to
    look at it; nothing here is human approval.
    """

    loaded = context if context is not None else GroundingContext(root)
    text_value = record.get("text")
    text = text_value if isinstance(text_value, str) else ""
    display = {normalize_math(item) for item in _display_statements(text)}
    found: list[dict[str, object]] = []
    seen: set[str] = set()
    premises: list[Definition] = []
    for kind, statement in math_statements(text):
        key = f"{kind}:{normalize_math(statement)}"
        if key in seen:
            continue
        seen.add(key)
        notes: dict[str, object] = {}
        status, evidence = _evidence(loaded, record, kind, statement, premises, notes)
        # A value or a condition ("x = 0", "r = R") holds at one place: it is never a premise for other relations.
        # An explicit definition (":=" or "\\equiv") is a premise as well: the author named what follows from it.
        if (kind == "claim" and status not in {"contradicted", "verification_failed", "value_or_condition"}) or kind == "definition":
            known = {item.name: item for item in premises}
            written = statement.replace(":=", "=").replace("\\equiv", "=") if kind == "definition" else statement
            definition = as_definition(written, known)
            # The first statement about a name defines it; a later one is a claim to check against it.
            if definition is not None and definition.name not in known:
                premises.append(definition)
        found.append(
            {
                "paragraph": record.get("id"),
                "section": record.get("section"),
                "statement": statement,
                "kind": kind,
                "status": status,
                "evidence": evidence,
                "important": normalize_math(statement) in display,
                "machine_parseable": _relation(statement) is not None or notes.get("calculus_readable") is True,
                "premises": notes.get("premises", []),
                "dimensions": loaded.dimension_probe(statement) if kind == "claim" and _relation(statement) is not None else None,
                "human_review": "required" if status in HUMAN_REVIEW_STATUSES - {"source_supported"}
                else ("recommended" if status == "source_supported" else "none"),
                "blocks_audit": status in BLOCKING_STATUSES,
            }
        )
    return found


def _display_statements(text: str) -> list[str]:
    statements: list[str] = []
    for match in _DISPLAY.finditer(text):
        groups = match.groups()
        body = (
            re.sub(r"\\(?:label|tag|nonumber|notag)\b(?:\{[^{}]*\})?", " ", groups[1])
            if groups[0] is not None and groups[1] is not None
            else next(group for group in groups[2:] if group is not None)
        )
        statements.extend(statement for _kind, statement in math_statements(f"${body}$"))
    return statements


def _status(context: GroundingContext, record: dict[str, object], kind: str, statement: str) -> str:
    return _evidence(context, record, kind, statement)[0]


def _evidence(
    context: GroundingContext,
    record: dict[str, object],
    kind: str,
    statement: str,
    premises: list[Definition] | None = None,
    notes: dict[str, object] | None = None,
) -> tuple[str, list[str]]:
    """The strongest status the stored evidence gives this exact statement, and that evidence.

    A relation the parser cannot read is never verified by a parser: only a
    cited excerpt (source support) or a stored check of the same text can back
    it. A failed check counts only when nothing passing backs the statement.
    """

    if kind == "definition":
        return "definition", []
    if kind == "approximation":
        return "approximation", []
    if kind == "condition":
        return "value_or_condition", []
    matrices = _matrix_verdict(statement)
    if matrices is not None:
        return matrices, []
    arithmetic = _arithmetic_verdict(statement)
    if arithmetic is not None:
        return arithmetic, []
    if _condition(statement):
        return "value_or_condition", []
    found: list[tuple[str, str]] = []
    failed: list[str] = []
    for excerpt_id in _string_list(record.get("excerpts")):
        excerpt = context.excerpts.get(excerpt_id)
        body = excerpt.get("text") if isinstance(excerpt, dict) else None
        check = excerpt.get("quote_check") if isinstance(excerpt, dict) else None
        if isinstance(check, dict) and check.get("status") == "client_transcription":
            # Typed from a page image: the server never saw those words, so they cannot support an equation.
            continue
        if isinstance(body, str) and _stated_in(statement, body):
            found.append(("source_supported", excerpt_id))
    for derivation in context.derivations(record.get("section")):
        identifier = str(derivation.get("id"))
        verification = derivation.get("verification")
        derivation_status = str(verification.get("status")) if isinstance(verification, dict) else "UNVERIFIED"
        covered, chained = _final_relations(derivation)
        if any(_same_relation(statement, line) for line in covered):
            if derivation_status in _DERIVATION_EVIDENCE:
                found.append((_DERIVATION_EVIDENCE[derivation_status], identifier))
            elif derivation_status == "FAILED":
                failed.append(identifier)
            continue
        if derivation_status in _DERIVATION_EVIDENCE and any(_same_relation(statement, line) for line in chained):
            # The equation states several relations and the check covers one of them, not necessarily this one.
            found.append(("derived_steps_unchecked", identifier))
            continue
        steps = derivation.get("steps_latex")
        lines = [line for line in steps if isinstance(line, str)] if isinstance(steps, list) else []
        if derivation_status in _DERIVATION_EVIDENCE and any(_same_relation(statement, line) for line in lines):
            found.append(("derived_steps_unchecked", identifier))
    for verification in context.verifications:
        inputs = verification.get("inputs")
        left = inputs.get("left") if isinstance(inputs, dict) else None
        right = inputs.get("right") if isinstance(inputs, dict) else None
        if not isinstance(left, str) or not isinstance(right, str) or not _same_relation(statement, f"{left} = {right}"):
            continue
        identifier = str(verification.get("id"))
        if verification.get("verification_status") == "SYMBOLICALLY_VERIFIED" and verification.get("ok") is True:
            found.append(("symbolically_verified", identifier))
        elif verification.get("verification_status") == "FAILED":
            failed.append(identifier)
    for computation in context.computations:
        if _computation_states(computation, statement):
            found.append(("numerically_reproduced", str(computation.get("id"))))
    for entry in declared_math(record):
        declared = entry.get("statement")
        if not isinstance(declared, str) or not _same_relation(statement, declared):
            continue
        refs = _string_list(entry.get("refs"))
        # The declaration was revalidated against these ids when it was stored.
        if entry.get("kind") == "source":
            found.extend(("source_supported", ref) for ref in refs)
        elif entry.get("kind") == "example":
            found.extend(("numerically_reproduced", ref) for ref in refs)
    held = min((_RANK[status] for status, _identifier in found), default=len(EQUATION_STATUSES))
    if kind == "claim" and held > _RANK["symbolically_verified"]:
        outcome = check_with_premises(statement, premises or [])
        if outcome is not None:
            if notes is not None:
                notes["calculus_readable"] = True
                notes["premises"] = list(outcome.premises)
            if outcome.kind == "contradiction":
                return "contradicted", ["sympy"]
            if outcome.kind == "identity":
                found.append(("follows_from_stated_premises" if outcome.premises else "symbolically_verified", "sympy"))
    if found:
        best = min(found, key=lambda item: _RANK[item[0]])[0]
        return best, sorted({identifier for _status, identifier in found})
    if failed:
        return "verification_failed", sorted(set(failed))
    return ("unsupported" if _relation(statement) is not None else "not_machine_checkable"), []


def _string_list(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _final_relations(derivation: dict[str, object]) -> tuple[list[str], list[str]]:
    """Relations a derivation's check is about, and relations that only share its equation.

    A derivation whose equation states one relation is covered by its check.
    When the equation states several (``a = b = c``, ``u(r) = ..., Q = ...``)
    the check verifies the stored symbolic residual, and which of the
    relations that residual encodes is not recorded, so none of them is
    covered individually. The symbolic form itself always is.
    """

    covered: list[str] = []
    chained: list[str] = []
    equation = derivation.get("equation")
    if isinstance(equation, str) and equation.strip():
        relations = [statement for kind, statement in math_statements(f"${equation.strip()}$") if kind == "claim"]
        if len(relations) <= 1:
            covered.append(equation.strip())
        else:
            chained.extend(relations)
    symbolic = derivation.get("symbolic")
    if isinstance(symbolic, str) and symbolic.strip():
        covered.append(symbolic.strip() if "=" in symbolic else f"{symbolic.strip()} = 0")
    return covered, chained


def _same_relation(statement: str, other: str) -> bool:
    """The same complete relation: equal text up to notation, or symbolically equivalent."""

    for _kind, candidate in math_statements(other if "$" in other or "\\(" in other else f"${other}$"):
        if normalize_math(statement) == normalize_math(candidate) or _canon(statement) == _canon(candidate):
            return True
        if _relation(statement) is not None and _relation(candidate) is not None and equivalent_math(statement, candidate):
            return True
    return False


_GREEK_LETTERS = {
    "α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "δ": r"\delta", "ε": r"\varepsilon", "ζ": r"\zeta", "η": r"\eta",
    "θ": r"\theta", "κ": r"\kappa", "λ": r"\lambda", "μ": r"\mu", "ν": r"\nu", "ξ": r"\xi", "π": r"\pi", "ρ": r"\rho",
    "σ": r"\sigma", "τ": r"\tau", "φ": r"\phi", "χ": r"\chi", "ψ": r"\psi", "ω": r"\omega",
    "Γ": r"\Gamma", "Δ": r"\Delta", "Θ": r"\Theta", "Λ": r"\Lambda", "Ξ": r"\Xi", "Π": r"\Pi", "Σ": r"\Sigma",
    "Φ": r"\Phi", "Ψ": r"\Psi", "Ω": r"\Omega",
}  # fmt: skip


def _plain_math(text: str) -> str:
    """An excerpt typed with Unicode Greek letters and square brackets, as LaTeX: ``τ / γ`` becomes ``\\tau / \\gamma``.

    Alignment marks are dropped and row breaks (``\\\\``) become separators, so ``a&=b\\\\ c&=d`` reads as two relations.
    """

    text = re.sub(r"\\\\(?:\[\d*(?:\.\d+)?(?:ex|em|pt|mm|cm)?\]?)?", " ; ", text).replace("&", "")
    text = re.sub(r"\\(?:begin|end)\{(?:aligned|align\*?|gathered|gather\*?|split|eqnarray\*?)\}", " ; ", text)
    text = re.sub(r"\\[cdt]frac(?![A-Za-z])", r"\\frac", text)
    out = []
    for index, character in enumerate(text):
        command = _GREEK_LETTERS.get(character)
        if command is None:
            out.append("(" if character == "[" else ")" if character == "]" else character)
            continue
        following = text[index + 1] if index + 1 < len(text) else ""
        out.append(command + (" " if following.isalnum() else ""))
    return "".join(out)


_TEX_OR_GREEK = re.compile("\\\\|[" + "".join(_GREEK_LETTERS) + "]")
_WORD = re.compile(r"(?!(?:dx|dy|dz|dt|ds|dA|dV)[,;:.]?$)(?:[A-Za-z]{2,}[,;:.]?|;)")


def _balanced(side: str) -> str:
    """Drop the unmatched outer braces a clipped LaTeX run leaves at its ends."""

    side = side.strip()
    while side.startswith("{") and side.count("{") > side.count("}"):
        side = side[1:].lstrip()
    while side.endswith("}") and side.count("}") > side.count("{"):
        side = side[:-1].rstrip()
    return side


def _chain_relations(body: str) -> list[str]:
    """Every pair of sides of a plain-text equality chain: ``a = b = c`` also states ``a = c``.

    A chain is a run of tokens around ``=`` that contains no English word (two or more bare letters).
    """

    tokens = _plain_math(body).split()
    pairs: list[str] = []
    index = 0
    while index < len(tokens):
        if _WORD.fullmatch(tokens[index]):
            index += 1
            continue
        end = index
        while end < len(tokens) and not _WORD.fullmatch(tokens[end]):
            end += 1
        run = " ".join(tokens[index:end]).strip(" .,;:")
        run = re.sub(r"^\.+\s*", "", run)
        sides = [side.strip() for side in re.split(r"(?<![<>!:=])=(?!=)", run)]
        if len(sides) >= 2:
            sides = [_balanced(side) for side in sides]
            pairs.extend(f"{sides[a]} = {sides[b]}" for a in range(len(sides)) for b in range(a + 1, len(sides)) if sides[a] and sides[b])
        index = end + 1
    return pairs


def _stated_in(statement: str, body: str) -> bool:
    """A cited excerpt states the whole relation, not a part of a longer one."""

    if any(_same_relation(statement, candidate) for kind, candidate in math_statements(body) if kind == "claim"):
        return True
    if (_TEX_OR_GREEK.search(body) is not None) and any(_same_relation(statement, pair) for pair in _chain_relations(body)):
        return True
    needle = normalize_math(statement)
    haystack = normalize_math(body)
    start = haystack.find(needle)
    while needle and start >= 0:
        before = haystack[start - 1] if start > 0 else ""
        after = haystack[start + len(needle)] if start + len(needle) < len(haystack) else ""
        if not _operand(before) and not _operand(after):
            return True
        start = haystack.find(needle, start + 1)
    return False


def _operand(character: str) -> bool:
    return bool(character) and (character.isalnum() or character in "_\\.+-*/^()=")


def _computation_states(computation: dict[str, object], statement: str) -> bool:
    expression = computation.get("expression")
    result = computation.get("server_result")
    if not isinstance(expression, str):
        return False
    if isinstance(result, str) and _same_relation(statement, f"{expression} = {result}"):
        return True
    left, _sign, right = statement.partition("=")
    return normalize_math(_latex_to_ascii(left)) == normalize_math(expression) and _numbers_only(right)


def _numbers_only(text: str) -> bool:
    return _arithmetic_text(text) is not None and not re.search(r"[*/+^()]", _arithmetic_text(text) or "")


def _arithmetic_text(side: str) -> str | None:
    """A LaTeX side as plain arithmetic (decimal commas, thin-space groups), or None if it has symbols."""

    text = side.replace("{,}", ".").replace("−", "-")
    text = re.sub(r"(?<=\d)(?:\\,|\\;|\\:|\\!|~|\s)+(?=\d{3}(?!\d))", "", text)
    text = text.replace(r"\left", "").replace(r"\right", "")
    text = re.sub(r"\\[,;:!]", "", text)
    text = text.replace(r"\cdot", "*").replace(r"\times", "*")
    for _ in range(3):
        text = re.sub(r"\\[dt]?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}", r"((\1)/(\2))", text)
    text = text.replace("^", "**").replace("{", "(").replace("}", ")").strip()
    if not text or re.search(r"[A-Za-z\\_]", text):
        return None
    # A typeset number in scientific notation is one value: 6.63×10^{-8}/1.0×10^{-5}
    # divides two numbers, it does not multiply the quotient by 10^{-5}.
    return re.sub(r"(\d+(?:\.\d+)?)\s*\*\s*10\s*\*\*\s*\(?\s*([+-]?\d+)\s*\)?", r"(\1e\2)", text)


_MATRIX = re.compile(r"\\begin\{([bpvBV]?matrix)\}(.*?)\\end\{\1\}", re.S)


def _matrix_verdict(statement: str) -> str | None:
    """Check a relation between numeric matrices (``K u = f`` written with numbers).

    Each matrix literal must hold only plain numbers; products, sums and
    scalar multiples are evaluated exactly. A literal result is compared entry
    by entry at its written precision. Anything with a symbol returns None.
    """

    if not _MATRIX.search(statement):
        return None
    import ast

    import sympy

    from studium.authoring.computation import ComputationError, evaluate, precision_verdict

    literals: dict[str, sympy.Matrix] = {}
    written: dict[str, list[list[str]]] = {}

    def replace(match: re.Match[str]) -> str:
        rows = [row for row in re.split(r"\\\\", match.group(2)) if row.strip()]
        table = [[cell.strip() for cell in row.split("&")] for row in rows]
        values = []
        for row in table:
            converted = []
            for cell in row:
                text = _arithmetic_text(cell)
                if text is None:
                    raise ValueError("symbolic entry")
                converted.append(text)
            values.append(converted)
        name = f"M{len(literals)}"
        literals[name] = sympy.Matrix([[sympy.Rational(evaluate(cell)) for cell in row] for row in values])
        written[name] = values
        return f" {name} "

    left, sign, right = statement.partition("=")
    if not sign:
        return None
    try:
        left_text = _MATRIX.sub(replace, left)
        right_text = _MATRIX.sub(replace, right)
    except (ValueError, ComputationError, ZeroDivisionError, TypeError):
        return None

    def value(side: str) -> object:
        text = _arithmetic_side(side)
        if text is None:
            raise ValueError("not arithmetic")
        tree = ast.parse(text, mode="eval")

        def walk(node: ast.AST) -> object:
            if isinstance(node, ast.Expression):
                return walk(node.body)
            if isinstance(node, ast.Name) and node.id in literals:
                return literals[node.id]
            if isinstance(node, ast.Constant) and type(node.value) in (int, float):
                return sympy.Rational(str(node.value))
            if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
                return -cast(Any, walk(node.operand))
            if isinstance(node, ast.BinOp):
                first, second = cast(Any, walk(node.left)), cast(Any, walk(node.right))
                if isinstance(node.op, ast.Add):
                    return first + second
                if isinstance(node.op, ast.Sub):
                    return first - second
                if isinstance(node.op, ast.Mult):
                    return first * second
                if isinstance(node.op, ast.Div) and not isinstance(second, sympy.MatrixBase):
                    return first / second
            raise ValueError("unsupported matrix expression")

        return walk(tree)

    try:
        first, second = value(left_text), value(right_text)
    except (ValueError, SyntaxError, TypeError, ZeroDivisionError, sympy.ShapeError):
        return None
    if not isinstance(first, sympy.MatrixBase) or not isinstance(second, sympy.MatrixBase):
        return None
    if first.shape != second.shape:
        return "contradicted"
    literal = right_text.strip() if right_text.strip() in written else None
    for index in range(first.rows * first.cols):
        actual = Fraction(str(first[index]))
        if literal is not None:
            row, column = divmod(index, first.cols)
            verdict = precision_verdict(written[literal][row][column].replace(" ", ""), actual)
        else:
            verdict = "agrees" if first[index] == second[index] else "disagrees"
        if verdict != "agrees":
            return "contradicted" if verdict == "disagrees" else "numerically_ambiguous"
    return "numerically_reproduced"


def _arithmetic_side(side: str) -> str | None:
    """A side made of matrix placeholders and numbers, in Python syntax."""

    text = side.replace(r"\cdot", "*").replace(r"\times", "*").replace("{,}", ".")
    text = re.sub(r"\\[,;:!]", " ", text)
    if re.search(r"[A-Za-z]", re.sub(r"\bM\d+\b", "", text)):
        return None
    text = re.sub(r"(?<=[\w)])\s+(?=[\w(])", "*", text.strip())
    return text


def _written_number(text: str) -> str | None:
    """One typeset number (``2.55``, or ``2.55e7`` once scientific notation is joined), else None.

    A claim written to a given precision is rounded to its last digit, so ``2.55×10^7`` agrees with 2.5516e7;
    it is read at that precision, never compared as an exact quotient.
    """

    plain = text.replace(" ", "")
    if plain.startswith("(") and plain.endswith(")"):
        plain = plain[1:-1]
    return plain if re.fullmatch(r"-?\d+(?:\.\d+)?(?:e[+-]?\d+)?", plain) else None


def _arithmetic_verdict(statement: str) -> str | None:
    """``numerically_reproduced`` / ``contradicted`` for a relation between plain numbers, else None."""

    from studium.authoring.computation import ComputationError, evaluate, precision_verdict

    left, sign, right = statement.partition("=")
    if not sign:
        return None
    left_text, right_text = _arithmetic_text(left), _arithmetic_text(right)
    if left_text is None or right_text is None:
        return None
    try:
        written_right, written_left = _written_number(right_text), _written_number(left_text)
        if written_right is not None:
            verdict = precision_verdict(written_right, evaluate(left_text))
        elif written_left is not None:
            verdict = precision_verdict(written_left, evaluate(right_text))
        else:
            first, second = evaluate(left_text), evaluate(right_text)
            verdict = "agrees" if abs(first - second) <= abs(second) * Fraction(1, 10**12) else "disagrees"
    except (ComputationError, ZeroDivisionError, OverflowError, ValueError):
        return None
    if verdict == "agrees":
        return "numerically_reproduced"
    if verdict == "ambiguous":
        return "numerically_ambiguous"
    return "contradicted"


def classify(root: Path, record: dict[str, object], formula: str) -> frozenset[str]:
    """The evidence status of one relation, as a set; empty when nothing supports it."""

    status = _status(GroundingContext(root), record, "claim", formula)
    return frozenset({status}) if status in GROUNDED_STATUSES else frozenset()


def ungrounded_formulas(root: Path, record: dict[str, object]) -> list[str]:
    """Relations that block the evidence audit: unsupported, contradicted, or with a failed check."""

    return [statement for statement, status in formula_statuses(root, record) if status in BLOCKING_STATUSES]


def grounding_summary(root: Path) -> dict[str, object]:
    """Count the prose relations by evidence status, and say whether verification is complete."""

    from studium.authoring.paragraphs import supported_paragraphs

    context = GroundingContext(root)
    by_status: dict[str, int] = dict.fromkeys(FORMULA_STATUSES, 0)
    total = 0
    blocking = 0
    claims = 0
    verified = 0
    unresolved_important: list[dict[str, object]] = []
    important_unresolved = 0
    dimensions: dict[str, int] = {"consistent": 0, "inconsistent": 0, "unavailable": 0}
    dimension_conflicts: list[dict[str, object]] = []
    declared: dict[str, int] = {"source": 0, "derivation": 0, "example": 0}
    for record in supported_paragraphs(root):
        for item in equation_evidence(root, record, context):
            total += 1
            status = str(item["status"])
            by_status[status] = by_status.get(status, 0) + 1
            if status in BLOCKING_STATUSES:
                blocking += 1
            probe = item.get("dimensions")
            if isinstance(probe, dict):
                outcome = str(probe.get("status"))
                dimensions[outcome] = dimensions.get(outcome, 0) + 1
                if outcome == "inconsistent" and status not in VERIFIED_STATUSES and len(dimension_conflicts) < 50:
                    dimension_conflicts.append(
                        {"paragraph": item["paragraph"], "statement": item["statement"], "detail": probe.get("detail")}
                    )
            if status in EQUATION_STATUSES:
                claims += 1
                if status in VERIFIED_STATUSES:
                    verified += 1
                elif item["important"]:
                    important_unresolved += 1
                    if len(unresolved_important) < 50:
                        unresolved_important.append({key: item[key] for key in ("paragraph", "statement", "status")})
        for entry in declared_math(record):
            kind = entry.get("kind")
            if kind in declared:
                declared[str(kind)] += 1
    checked = 0
    for derivation in context.derivation_records:
        verification = derivation.get("verification")
        if isinstance(verification, dict) and str(verification.get("status")) in VERIFIED_DERIVATION_STATUSES:
            checked += 1
    return {
        "formulas": total,
        "claims": claims,
        "claims_verified": verified,
        "formulas_ungrounded": blocking,
        "by_status": by_status,
        "by_kind": {
            "source": by_status["source_supported"],
            "derivation": by_status["symbolically_verified"] + by_status["dimensionally_verified"],
            "example": by_status["numerically_reproduced"],
        },
        "scientific_verification_complete": claims == verified,
        "unresolved_important": unresolved_important,
        "unresolved_important_count": important_unresolved,
        "dimension_probe": dimensions,
        "dimension_conflicts": dimension_conflicts,
        "declared": declared,
        "checked_derivations": checked,
        "note": (
            "Statuses describe stored evidence for each exact statement. Source support is not a proof, "
            "not_machine_checkable is not an error, and nothing here is human approval."
        ),
    }


def equation_report(root: Path, *, section: object = None, status: object = None, offset: object = 0, limit: object = 100) -> dict[str, object]:
    """Every prose equation with its exact statement, evidence status and evidence ids (paginated).

    Read-only. ``section`` and ``status`` filter; ``status`` may be one status
    or a list. Nothing in the report is verification by a person.
    """

    from studium.authoring.paragraphs import supported_paragraphs

    wanted = {status} if isinstance(status, str) else ({item for item in status if isinstance(item, str)} if isinstance(status, list) else None)
    if wanted is not None and not wanted <= set(FORMULA_STATUSES):
        return _error("mcp.invalid_input", "status must be one of: " + ", ".join(FORMULA_STATUSES))
    start = offset if isinstance(offset, int) and not isinstance(offset, bool) and offset >= 0 else 0
    size = limit if isinstance(limit, int) and not isinstance(limit, bool) and 1 <= limit <= 500 else 100
    context = GroundingContext(root)
    rows: list[dict[str, object]] = []
    for record in supported_paragraphs(root):
        if isinstance(section, str) and record.get("section") != section:
            continue
        for item in equation_evidence(root, record, context):
            if wanted is None or item["status"] in wanted:
                rows.append(item)
    return {
        "status": "ok",
        "total": len(rows),
        "offset": start,
        "equations": rows[start : start + size],
        "next_offset": start + size if start + size < len(rows) else None,
        "statuses": list(FORMULA_STATUSES),
        "note": (
            "Each status names the stored evidence for that exact statement. Source support is not a proof; "
            "not_machine_checkable needs human review; nothing here is human approval."
        ),
    }


def _derivation(root: Path, identifier: str) -> dict[str, object] | None:
    for record in fold_by_id(root / DERIVATIONS):
        if record.get("id") == identifier and record.get("deleted") is not True:
            return record
    return None


def _computation(root: Path, identifier: str) -> dict[str, object] | None:
    return next((record for record in fold_by_id(root / COMPUTATIONS) if record.get("id") == identifier), None)


def derivation_fingerprint(record: dict[str, object]) -> str:
    """Fingerprint of the parts of a derivation a paragraph declaration relies on.

    The verified status and the deterministic checks are included, so a new
    check with different values makes a dependent audit stale. ``checked_at``
    is excluded: rerecording the same check does not change the mathematics.
    """

    verification = record.get("verification")
    digestible = None
    if isinstance(verification, dict):
        digestible = {key: value for key, value in verification.items() if key != "checked_at"}
    payload = "\n".join(
        [
            str(record.get("equation") or ""),
            str(record.get("symbolic") or ""),
            json_lines(record.get("steps_latex")),
            json.dumps(digestible, ensure_ascii=False, sort_keys=True, default=str),
        ]
    )
    import hashlib

    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def json_lines(value: object) -> str:
    return "\n".join(item for item in value if isinstance(item, str)) if isinstance(value, list) else ""


def _computation_numbers(record: dict[str, object]) -> set[str]:
    found: set[str] = set()
    expression = record.get("expression")
    if isinstance(expression, str):
        found.update(_canon_number(item) for item in re.findall(r"-?\d+(?:\.\d+)?", expression))
    result = record.get("server_result")
    if isinstance(result, str):
        found.add(_canon_number(result))
    return found


def _canon_number(value: str) -> str:
    text = value.strip()
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in {"", "-"}:
        return "0"
    if text.startswith("+"):
        text = text[1:]
    return text


def _error(code: str, message: str) -> dict[str, object]:
    return {"status": code, "message": message}
