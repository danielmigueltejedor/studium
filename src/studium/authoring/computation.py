"""Replay a calculation. The reported number is not evidence.

The server stores the expression and the reported result, then evaluates the
expression itself. The result is accepted only when that evaluation matches.
Acceptance is ``replayed``, not verified, and it is not absolute truth.
"""

import ast
import hashlib
import math
import re
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path

from studium.authoring.blueprint import current_sections
from studium.authoring.excerpts import excerpts_by_id
from studium.authoring.paragraphs import supported_paragraphs
from studium.policy.trust import directive_changes_policy
from studium.storage.init_project import load_state, load_state_holding_lock
from studium.storage.locking import ProjectLocked, project_lock
from studium.storage.migrate import utc_now
from studium.storage.records import COMPUTATIONS, allocate_id, append_jsonl, fold_by_id

_AUDIT = "audit/audit.jsonl"
_MAX_EXPRESSION = 500
_MAX_EXPONENT = 20
_MAX_ABS = Fraction(10) ** 12


class ComputationError(Exception):
    """The expression is not a calculation the server can replay."""


_SUPPORTED = (
    "supported: numbers, + - * / **, parentheses, pi, e, and "
    "sqrt, cbrt, exp, log (natural), ln, log10, sin, cos, tan, asin, acos, atan, sinh, cosh, tanh, abs"
)

_FUNCTIONS = {
    "sqrt": math.sqrt,
    "cbrt": math.cbrt,
    "exp": math.exp,
    "log": math.log,
    "ln": math.log,
    "log10": math.log10,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "sinh": math.sinh,
    "cosh": math.cosh,
    "tanh": math.tanh,
}

_CONSTANTS = {"pi": math.pi, "e": math.e}


def evaluate(expression: str) -> Fraction:
    """Evaluate a numeric expression; see :func:`evaluate_number`."""

    return evaluate_number(expression)[0]


def evaluate_number(expression: str) -> tuple[Fraction, bool]:
    """Evaluate a numeric expression and say whether the result is exact.

    Rational arithmetic with integer powers stays exact. Roots, non-integer
    powers, the constants pi and e, and the allowlisted functions are evaluated
    in floating point, and the result is marked inexact. Names other than those,
    attributes, and any other call are rejected.
    """

    if not isinstance(expression, str):
        raise ComputationError("expression is required")
    cleaned = expression.strip()
    if not cleaned or len(cleaned) > _MAX_EXPRESSION:
        raise ComputationError("expression is required")
    if any(character in cleaned for character in ";|&$`\n\r") or "\\" in cleaned:
        raise ComputationError("expression is not a calculation")
    lowered = cleaned.lower()
    if "http://" in lowered or "https://" in lowered:
        raise ComputationError("expression must not fetch a URL")
    try:
        tree = ast.parse(cleaned, mode="eval")
    except SyntaxError as exc:
        raise ComputationError("expression is not a calculation") from exc
    if not isinstance(tree, ast.Expression):
        raise ComputationError("expression is not a calculation")
    return _eval(tree.body)


def agrees(claimed: object, actual: Fraction) -> bool:
    """Whether a claimed number is ``actual`` written to the claim's own precision.

    A claim is read as rounded to its last written digit: ``31.30`` agrees with
    31.2998 and ``3924`` agrees only with values within half a unit of 3924.
    An integer with three or more trailing zeros (``83300000``) is read to its last
    non-zero digit, because those zeros are placeholders.
    """

    if isinstance(claimed, Fraction):
        written_text = _terminating_decimal(claimed)
        if written_text is None:
            return claimed == actual
        claimed = written_text
    try:
        written = Decimal(str(claimed).strip())
    except (InvalidOperation, ValueError):
        return False
    if not written.is_finite():
        return False
    if Fraction(written) == actual:
        return True
    exponent = written.as_tuple().exponent
    if not isinstance(exponent, int):
        return False
    if exponent == 0 and written != 0 and "e" not in str(claimed).lower():
        # "83300000" cannot say how many of its zeros are significant. From three
        # trailing zeros on they are read as placeholders and the last non-zero
        # digit sets the precision. "3920" and "30" keep the strict reading.
        trimmed = written.normalize().as_tuple().exponent
        if isinstance(trimmed, int) and trimmed >= 3:
            exponent = trimmed
    half_unit = Fraction(1, 2) * Fraction(10) ** exponent
    slack = abs(actual) * Fraction(1, 10**12)
    return abs(actual - Fraction(written)) <= half_unit + slack


def check_computation(
    root: Path,
    *,
    expression: object = None,
    result: object = None,
    computation_id: object = None,
    section: object = None,
    actor: dict[str, object] | None = None,
) -> dict[str, object]:
    """Store a calculation and accept it only after the server evaluates it again.

    A stored ``replayed`` flag is not trusted. Every call evaluates the expression.
    """

    identifier = _identifier(computation_id)
    if computation_id is not None and identifier is None:
        return _error("mcp.invalid_input", "id is required")
    if identifier is not None:
        return _replay(root, identifier, expression, actor)
    parsed, claimed, section_id, error = _new_inputs(root, expression, result, section)
    if error is not None:
        return error
    assert parsed is not None and claimed is not None
    try:
        server_result = evaluate(parsed)
    except ComputationError as exc:
        return _error("computation.invalid", str(exc))
    refusal = _small_integer_refusal(root, parsed, section_id)
    if refusal is not None:
        return refusal
    return _store(
        root,
        identifier=None,
        expression=parsed,
        claimed=claimed,
        server_result=server_result,
        section_id=section_id,
        actor=actor,
    )


def list_computations(root: Path) -> list[dict[str, object]]:
    """Stored calculations. A matching report is replayed, not verified."""

    return [_public(record) for record in fold_by_id(root / COMPUTATIONS)]


def _replay(
    root: Path,
    identifier: str,
    expression: object,
    actor: dict[str, object] | None,
) -> dict[str, object]:
    current = next((item for item in fold_by_id(root / COMPUTATIONS) if item.get("id") == identifier), None)
    if current is None:
        return _error("computation.not_found", "no stored computation with that id")
    stored_expression = current.get("expression")
    claimed_text = current.get("claimed_result")
    if not isinstance(stored_expression, str) or not isinstance(claimed_text, str):
        return _error("computation.invalid", "the stored computation cannot be replayed")
    if expression is not None and (
        not isinstance(expression, str) or expression.strip() != stored_expression
    ):
        return _error("computation.expression_changed", "replay evaluates the stored expression")
    claimed = _fraction(claimed_text)
    if claimed is None:
        return _error("computation.invalid", "the stored result is not numeric")
    try:
        server_result = evaluate(stored_expression)
    except ComputationError as exc:
        return _error("computation.invalid", str(exc))
    section_value = current.get("section")
    section = section_value if isinstance(section_value, str) else None
    refusal = _small_integer_refusal(root, stored_expression, section)
    if refusal is not None:
        return refusal
    return _store(
        root,
        identifier=identifier,
        expression=stored_expression,
        claimed=claimed,
        server_result=server_result,
        section_id=section,
        actor=actor,
    )


def _store(
    root: Path,
    *,
    identifier: str | None,
    expression: str,
    claimed: Fraction,
    server_result: Fraction,
    section_id: str | None,
    actor: dict[str, object] | None,
) -> dict[str, object]:
    matched = agrees(claimed, server_result)
    try:
        with project_lock(root):
            record_id = identifier if identifier is not None else allocate_id(root, "PRB")
            record: dict[str, object] = {
                "schema_version": "1.0.0",
                "id": record_id,
                "kind": "computation",
                "expression": expression,
                "claimed_result": _canonical(claimed),
                "server_result": _canonical(server_result),
                "status": "replayed" if matched else "mismatch",
                "correct": matched,
                "classification": "PENDING",
                "recorded_at": utc_now(),
            }
            if matched:
                record["corroboration"] = "replayed"
            if section_id is not None:
                record["section"] = section_id
            record["input_sha256"] = computation_fingerprint(record)
            append_jsonl(root / COMPUTATIONS, record)
            _audit(root, record=record, actor=actor)
            fresh = load_state_holding_lock(root)
    except ProjectLocked:
        return _error("storage.locked", "project is locked")
    body = _body(fresh, record, matched=matched)
    if not matched:
        body["message"] = "The server evaluated a different result. The reported number was not accepted."
    return body


def _small_integer_refusal(root: Path, expression: str, section_id: str | None) -> dict[str, object] | None:
    """Reject toy arithmetic unless one cited excerpt contains every number."""

    numbers = _small_integer_numbers(expression)
    if numbers is None or _cited_excerpt_has_numbers(root, section_id, numbers):
        return None
    state = load_state(root)
    return {
        "status": "computation.ungrounded",
        "message": "The expression is only small-integer arithmetic and its numbers are not in a cited excerpt.",
        "accepted": False,
        "correct": False,
        "released": state.get("state") == "RELEASED",
        "applied": False,
    }


def _small_integer_numbers(expression: str) -> set[str] | None:
    """Integers combined with + - * / . A decimal, name, power, or unit is not this class."""

    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError:
        return None
    if not isinstance(tree, ast.Expression):
        return None
    numbers: set[str] = set()
    ok, binary = _walk_small(tree.body, numbers, False)
    if not ok or not binary or not numbers:
        return None
    return numbers


def _walk_small(node: ast.AST, numbers: set[str], binary: bool) -> tuple[bool, bool]:
    if isinstance(node, ast.Constant):
        value = node.value
        if isinstance(value, bool) or not isinstance(value, int):
            return False, binary
        numbers.add(str(value))
        return True, binary
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        return _walk_small(node.operand, numbers, binary)
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
        left_ok, _left_binary = _walk_small(node.left, numbers, True)
        if not left_ok:
            return False, True
        return _walk_small(node.right, numbers, True)
    return False, binary


def _cited_excerpt_has_numbers(root: Path, section_id: str | None, numbers: set[str]) -> bool:
    stored = excerpts_by_id(root)
    for paragraph in supported_paragraphs(root):
        if section_id is not None and paragraph.get("section") != section_id:
            continue
        excerpt_ids = paragraph.get("excerpts")
        if not isinstance(excerpt_ids, list):
            continue
        for excerpt_id in excerpt_ids:
            if not isinstance(excerpt_id, str):
                continue
            record = stored.get(excerpt_id)
            if not isinstance(record, dict):
                continue
            text = record.get("text")
            if isinstance(text, str) and all(_number_in_text(text, number) for number in numbers):
                return True
    return False


def _number_in_text(text: str, number: str) -> bool:
    return re.search(rf"(?<!\d){re.escape(number)}(?!\d)", text) is not None


def _new_inputs(
    root: Path,
    expression: object,
    result: object,
    section: object,
) -> tuple[str | None, Fraction | None, str | None, dict[str, object] | None]:
    if not isinstance(expression, str) or not expression.strip():
        return None, None, None, _error("mcp.invalid_input", "expression is required")
    parsed = expression.strip()
    if directive_changes_policy(parsed):
        return None, None, None, _error("policy.overridden", "expression changed policy")
    claimed = _reported(result)
    if claimed is None:
        return None, None, None, _error("mcp.invalid_input", "result is required")
    section_id, section_error = _section(root, section)
    if section_error is not None:
        return None, None, None, section_error
    return parsed, claimed, section_id, None


def _terminating_decimal(value: Fraction) -> str | None:
    """The shortest decimal that is exactly ``value``, or None for a repeating one."""

    denominator = value.denominator
    places = 0
    while denominator % 10 == 0 or denominator % 2 == 0 or denominator % 5 == 0:
        if places > 40:
            return None
        places += 1
        scaled = value * 10**places
        if scaled.denominator == 1:
            text = str(abs(scaled.numerator)).rjust(places + 1, "0")
            sign = "-" if value < 0 else ""
            return f"{sign}{text[:-places]}.{text[-places:]}"
        denominator = scaled.denominator
    return str(value.numerator) if value.denominator == 1 else None


def _eval(node: ast.AST) -> tuple[Fraction, bool]:
    if isinstance(node, ast.Constant):
        return _constant(node.value), True
    if isinstance(node, ast.Name):
        if node.id in _CONSTANTS:
            return _bounded(Fraction(_CONSTANTS[node.id])), False
        raise ComputationError(f"{node.id!r} is not a number; {_SUPPORTED}")
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value, exact = _eval(node.operand)
        return _bounded(value if isinstance(node.op, ast.UAdd) else -value), exact
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
        left, left_exact = _eval(node.left)
        right, right_exact = _eval(node.right)
        exact = left_exact and right_exact
        if isinstance(node.op, ast.Add):
            return _bounded(left + right), exact
        if isinstance(node.op, ast.Sub):
            return _bounded(left - right), exact
        if isinstance(node.op, ast.Mult):
            return _bounded(left * right), exact
        if isinstance(node.op, ast.Div):
            if right == 0:
                raise ComputationError("expression divides by zero")
            return _bounded(left / right), exact
        return _power(left, right, exact)
    if isinstance(node, ast.Call):
        name = node.func.id if isinstance(node.func, ast.Name) else None
        if name is None or node.keywords or len(node.args) != 1 or (name != "abs" and name not in _FUNCTIONS):
            raise ComputationError(f"expression is not a calculation; {_SUPPORTED}")
        argument, exact = _eval(node.args[0])
        if name == "abs":
            return abs(argument), exact
        try:
            result = _FUNCTIONS[name](float(argument))
        except (ValueError, OverflowError) as exc:
            raise ComputationError(f"the value is outside the domain of {name} or the replay limit") from exc
        return _float(result), False
    raise ComputationError(f"expression is not a calculation; {_SUPPORTED}")


def _power(base: Fraction, exponent: Fraction, exact: bool) -> tuple[Fraction, bool]:
    if exponent.denominator == 1 and abs(exponent) <= _MAX_EXPONENT:
        if base == 0 and exponent < 0:
            raise ComputationError("expression divides by zero")
        return _bounded(base ** int(exponent)), exact
    if base < 0:
        raise ComputationError("a negative base with a non-integer exponent is outside the replay limit")
    try:
        result = float(base) ** float(exponent)
    except (ValueError, OverflowError, ZeroDivisionError) as exc:
        raise ComputationError("the power is outside the replay limit") from exc
    return _float(result), False


def _float(value: float) -> Fraction:
    if not math.isfinite(value):
        raise ComputationError("the result is outside the replay limit")
    return _bounded(Fraction(value))


def _constant(value: object) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ComputationError("expression is not a calculation")
    try:
        parsed = Fraction(value) if isinstance(value, int) else Fraction(str(value))
    except (ValueError, OverflowError) as exc:
        raise ComputationError("expression is not a calculation") from exc
    if parsed.denominator == 0:
        raise ComputationError("expression is not a calculation")
    return _bounded(parsed)


def _bounded(value: Fraction) -> Fraction:
    if abs(value) > _MAX_ABS:
        raise ComputationError("result is outside the replay limit")
    return value


def _reported(value: object) -> Fraction | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return Fraction(value)
    if isinstance(value, float):
        try:
            return Fraction(str(value))
        except (ValueError, OverflowError):
            return None
    if isinstance(value, str):
        return _fraction(value.strip())
    return None


def _fraction(value: str) -> Fraction | None:
    if not value or len(value) > 80:
        return None
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError):
        return None


def computation_fingerprint(record: dict[str, object]) -> str:
    """Fingerprint of the expression and the result an audit is allowed to cite."""

    payload = "\n".join(
        [
            str(record.get("expression") or ""),
            str(record.get("server_result") or ""),
            str(record.get("status") or ""),
            str(record.get("correct")),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _canonical(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def _section(root: Path, value: object) -> tuple[str | None, dict[str, object] | None]:
    if value is None:
        return None, None
    if not isinstance(value, str) or not value.strip():
        return None, _error("mcp.invalid_input", "section must be a blueprint section id")
    identifier = value.strip()
    known = {section["id"] for section in current_sections(root)}
    if identifier not in known:
        return None, _error("computation.section_unknown", "section is not in the stored blueprint")
    return identifier, None


def _identifier(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or len(cleaned) > 128:
        return None
    return cleaned


def _public(record: dict[str, object]) -> dict[str, object]:
    visible = {
        "id": record.get("id"),
        "kind": "computation",
        "expression": record.get("expression"),
        "claimed_result": record.get("claimed_result"),
        "server_result": record.get("server_result"),
        "status": "replayed" if record.get("status") == "replayed" and record.get("correct") is True else "mismatch",
        "correct": record.get("correct") is True,
        "classification": "PENDING",
    }
    if record.get("corroboration") == "replayed" and visible["correct"] is True:
        visible["corroboration"] = "replayed"
    if isinstance(record.get("section"), str):
        visible["section"] = record["section"]
    return visible


def _body(state: dict[str, object], record: dict[str, object], *, matched: bool) -> dict[str, object]:
    visible = _public(record)
    return {
        "status": "replayed" if matched else "mismatch",
        "accepted": matched,
        "correct": matched,
        "expression": visible.get("expression"),
        "claimed_result": visible.get("claimed_result"),
        "server_result": visible.get("server_result"),
        "computation": visible,
        "local_sources": _local(state),
        "project_state": state.get("state"),
        "released": state.get("state") == "RELEASED",
    }


def _audit(root: Path, *, record: dict[str, object], actor: dict[str, object] | None) -> None:
    digest = hashlib.sha256(str(record.get("expression", "")).encode("utf-8")).hexdigest()
    append_jsonl(
        root / _AUDIT,
        {
            "schema_version": "1.0.0",
            "timestamp": utc_now(),
            "source_id": record.get("id"),
            "operation": "check_computation",
            "origin": None,
            "actor": {"kind": actor.get("kind")} if isinstance(actor, dict) and isinstance(actor.get("kind"), str) else None,
            "previous_hash": None,
            "new_hash": digest,
            "result": record.get("status"),
            "tool": "computation_check",
        },
    )


def _local(state: dict[str, object]) -> dict[str, object]:
    local = state.get("local_sources")
    if isinstance(local, dict):
        return dict(local)
    return {"status": "UNKNOWN", "prompted": False, "source_count": 0}


def _error(code: str, message: str) -> dict[str, object]:
    return {"status": code, "message": message, "accepted": False, "correct": False}
