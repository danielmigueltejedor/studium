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

    import sympy

    first = _relation(left)
    second = _relation(right)

    if first is None or second is None:
        return False

    try:
        first_num, _ = sympy.fraction(sympy.together(first))
        second_num, _ = sympy.fraction(sympy.together(second))

        if sympy.simplify(first_num - second_num) == 0:
            return True

        if sympy.simplify(first_num + second_num) == 0:
            return True

        if second_num == 0:
            return False

        ratio = sympy.cancel(first_num / second_num)

        return bool(ratio.is_number and ratio.is_nonzero is True)

    except (TypeError, ValueError, ZeroDivisionError, AttributeError):
        return False


@lru_cache(maxsize=4096)
def _relation(equation: str):
    """Parse a restricted algebraic equality without evaluating Python code."""
    import ast

    import sympy

    text = _latex_to_ascii(equation)

    if len(text) > 300 or text.count("=") != 1:
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
                return sympy.Symbol(node.id)

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
                    if b.is_Integer is not True or abs(int(b)) > 8:
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


#: Statuses a prose relation can have. Only the blocking ones stop an audit:
#: a parseable claim nothing stores, and arithmetic that does not hold.
GROUNDED_STATUSES = frozenset({"source", "derivation", "example"})
BLOCKING_STATUSES = frozenset({"ungrounded", "arithmetic_mismatch"})
FORMULA_STATUSES = (
    "source",
    "derivation",
    "example",
    "arithmetic",
    "arithmetic_ambiguous",
    "condition",
    "derivation_step",
    "definition",
    "approximation",
    "not_checkable",
    "ungrounded",
    "arithmetic_mismatch",
)

_SPAN = re.compile(r"\$\$(.+?)\$\$|\\\[(.+?)\\\]|\\\((.+?)\\\)|\$([^$]+)\$", re.S)
_RELATION_OPS = re.compile(r"\\approx|\\simeq|\\equiv|:=|(?<![<>!\\])=")
_OP_KINDS = {"=": "claim", "\\approx": "approximation", "\\simeq": "approximation", "\\equiv": "definition", ":=": "definition"}
_TRAILING = " ,;.:"


def math_statements(text: str) -> list[tuple[str, str]]:
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
        body = next(group for group in match.groups() if group is not None)
        for piece in _top_level_pieces(body):
            parts, operators = _split_relations(piece)
            for index, operator in enumerate(operators):
                left = parts[index].strip().strip(_TRAILING).strip()
                right = parts[index + 1].strip().strip(_TRAILING).strip()
                if _complete_side(left, -1) and _complete_side(right, 1) and not _elided(left) and not _elided(right):
                    found.append((_OP_KINDS[operator], f"{left} {operator} {right}"))
    outside.append(text[last:])
    for sentence in sentences(" ".join(outside)):
        for formula in formulas(sentence):
            left, _sign, right = formula.partition("=")
            if _complete_side(left, -1) and _complete_side(right, 1):
                found.append(("claim", formula))
    return found


_SEPARATORS = re.compile(r"\\q?quad\b|\\\\|&|;|,(?=\s|\\)|:(?=\s|\\)|\\(?:text|mbox|mathrm)\{[^{}]*\s[^{}]*\}")


def _top_level_pieces(body: str) -> list[str]:
    """Split a math span at top-level separators (``\\quad``, ``,\\ ``, ``;``, ``\\text{ y }``, ``\\\\``)."""

    pieces: list[str] = []
    depth = 0
    last = 0
    index = 0
    while index < len(body):
        character = body[index]
        if character in "{(":
            depth += 1
        elif character in "})":
            depth -= 1
        elif depth == 0:
            match = _SEPARATORS.match(body, index)
            if match:
                pieces.append(body[last:index])
                last = index = match.end()
                continue
        index += 1
    pieces.append(body[last:])
    return [piece for piece in pieces if piece.strip()]


def _split_relations(body: str) -> tuple[list[str], list[str]]:
    parts: list[str] = []
    operators: list[str] = []
    depth = 0
    last = 0
    index = 0
    while index < len(body):
        character = body[index]
        if character in "{(":
            depth += 1
        elif character in "})":
            depth -= 1
        elif depth == 0:
            match = _RELATION_OPS.match(body, index)
            if match:
                parts.append(body[last:index])
                operators.append(match.group(0))
                last = index = match.end()
                continue
        index += 1
    parts.append(body[last:])
    return parts, operators


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
    sides = []
    for side in (left, right):
        number = _arithmetic_text(side)
        text = number if number is not None else _latex_to_ascii(side).strip()
        sides.append(text.strip("()"))
    return all(_ATOM.fullmatch(side) for side in sides)


class GroundingContext:
    """What a relation may be grounded by, read once for many relations."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.excerpts = excerpts_by_id(root)
        self.computations = replayed_computations(root)
        self._derivations: dict[str, list[dict[str, object]]] = {}

    def derivations(self, section: object) -> list[dict[str, object]]:
        key = section if isinstance(section, str) else ""
        if key not in self._derivations:
            self._derivations[key] = verified_derivations(self.root, section)
        return self._derivations[key]


def formula_statuses(
    root: Path, record: dict[str, object], context: GroundingContext | None = None
) -> list[tuple[str, str]]:
    """Each complete relation the record states, with how it is grounded."""

    loaded = context if context is not None else GroundingContext(root)
    text_value = record.get("text")
    text = text_value if isinstance(text_value, str) else ""
    statuses: list[tuple[str, str]] = []
    seen: set[str] = set()
    for kind, statement in math_statements(text):
        key = f"{kind}:{normalize_math(statement)}"
        if key in seen:
            continue
        seen.add(key)
        statuses.append((statement, _status(loaded, record, kind, statement)))
    return statuses


def _status(context: GroundingContext, record: dict[str, object], kind: str, statement: str) -> str:
    if kind == "definition":
        return "definition"
    if kind == "approximation":
        return "approximation"
    arithmetic = _arithmetic_verdict(statement)
    if arithmetic is not None:
        return arithmetic
    if _condition(statement):
        return "condition"
    for body in record_excerpt_texts(record, context.excerpts):
        if _stated_in(statement, body):
            return "source"
    derivations = context.derivations(record.get("section"))
    for derivation in derivations:
        if any(_same_relation(statement, line) for line in _final_statements(derivation)):
            return "derivation"
    for computation in context.computations:
        if _computation_states(computation, statement):
            return "example"
    for entry in declared_math(record):
        declared = entry.get("statement")
        if isinstance(declared, str) and _same_relation(statement, declared) and entry.get("kind") in MATH_KINDS:
            return str(entry["kind"])
    for derivation in derivations:
        steps = derivation.get("steps_latex")
        lines = [line for line in steps if isinstance(line, str)] if isinstance(steps, list) else []
        if any(_same_relation(statement, line) for line in lines):
            return "derivation_step"
    return "ungrounded" if _relation(statement) is not None else "not_checkable"


def _final_statements(derivation: dict[str, object]) -> list[str]:
    """The equation a derivation check is about: the final equation and its symbolic form."""

    lines: list[str] = []
    equation = derivation.get("equation")
    if isinstance(equation, str) and equation.strip():
        lines.append(equation.strip())
    symbolic = derivation.get("symbolic")
    if isinstance(symbolic, str) and symbolic.strip():
        lines.append(symbolic.strip() if "=" in symbolic else f"{symbolic.strip()} = 0")
    return lines


def _same_relation(statement: str, other: str) -> bool:
    """The same complete relation: equal text up to notation, or symbolically equivalent."""

    for _kind, candidate in math_statements(other if "$" in other or "\\(" in other else f"${other}$"):
        if normalize_math(statement) == normalize_math(candidate) or _canon(statement) == _canon(candidate):
            return True
        if _relation(statement) is not None and _relation(candidate) is not None and equivalent_math(statement, candidate):
            return True
    return False


def _stated_in(statement: str, body: str) -> bool:
    """A cited excerpt states the whole relation, not a part of a longer one."""

    if any(_same_relation(statement, candidate) for kind, candidate in math_statements(body) if kind == "claim"):
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


def _arithmetic_verdict(statement: str) -> str | None:
    """``arithmetic`` / ``arithmetic_mismatch`` for a relation between plain numbers, else None."""

    from studium.authoring.computation import ComputationError, evaluate, precision_verdict

    left, sign, right = statement.partition("=")
    if not sign:
        return None
    left_text, right_text = _arithmetic_text(left), _arithmetic_text(right)
    if left_text is None or right_text is None:
        return None
    try:
        if re.fullmatch(r"-?\d+(?:\.\d+)?", right_text.replace(" ", "")):
            verdict = precision_verdict(right_text.replace(" ", ""), evaluate(left_text))
        elif re.fullmatch(r"-?\d+(?:\.\d+)?", left_text.replace(" ", "")):
            verdict = precision_verdict(left_text.replace(" ", ""), evaluate(right_text))
        else:
            first, second = evaluate(left_text), evaluate(right_text)
            verdict = "agrees" if abs(first - second) <= abs(second) * Fraction(1, 10**12) else "disagrees"
    except (ComputationError, ZeroDivisionError, OverflowError, ValueError):
        return None
    if verdict == "agrees":
        return "arithmetic"
    if verdict == "ambiguous":
        return "arithmetic_ambiguous"
    return "arithmetic_mismatch"


def classify(root: Path, record: dict[str, object], formula: str) -> frozenset[str]:
    """How one complete relation in prose is grounded. An empty set means not grounded.

    Only a cited excerpt stating the whole relation, the final equation of a
    checked derivation, a replayed computation, or a revalidated declaration
    grounds it. A derivation step is not checked and does not ground.
    """

    status = _status(GroundingContext(root), record, "claim", formula)
    return frozenset({status}) if status in GROUNDED_STATUSES else frozenset()


def ungrounded_formulas(root: Path, record: dict[str, object]) -> list[str]:
    """Relations that block an audit: a parseable claim nothing grounds, or arithmetic that does not hold."""

    return [statement for statement, status in formula_statuses(root, record) if status in BLOCKING_STATUSES]


def grounding_summary(root: Path) -> dict[str, object]:
    """Count the prose relations by status and the explicit declarations by kind."""

    from studium.authoring.paragraphs import supported_paragraphs

    context = GroundingContext(root)
    by_kind: dict[str, int] = {"source": 0, "derivation": 0, "example": 0}
    by_status: dict[str, int] = dict.fromkeys(FORMULA_STATUSES, 0)
    ungrounded = 0
    total = 0
    declared: dict[str, int] = {"source": 0, "derivation": 0, "example": 0}
    for record in supported_paragraphs(root):
        for _statement, status in formula_statuses(root, record, context):
            total += 1
            by_status[status] = by_status.get(status, 0) + 1
            if status in by_kind:
                by_kind[status] += 1
            if status in BLOCKING_STATUSES:
                ungrounded += 1
        for entry in declared_math(record):
            kind = entry.get("kind")
            if kind in declared:
                declared[str(kind)] += 1
    verified_derivations = 0
    for record in fold_by_id(root / DERIVATIONS):
        verification = record.get("verification")
        if isinstance(verification, dict) and str(verification.get("status")) in VERIFIED_DERIVATION_STATUSES:
            verified_derivations += 1
    return {
        "formulas": total,
        "formulas_ungrounded": ungrounded,
        "by_kind": by_kind,
        "by_status": by_status,
        "declared": declared,
        "checked_derivations": verified_derivations,
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
