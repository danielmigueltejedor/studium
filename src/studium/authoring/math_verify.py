"""The ``studium_math_verify`` tool: prove small mathematical claims.

The engine itself is in :mod:`studium.verification`. This module adds
persistence, auditing, and the same locked-write discipline used by
computations and problems. A stored record keeps the status, the method, the
assumptions and the limitations next to the inputs, so a later renderer can
label the claim exactly as strongly as it was checked.

Like every other Studium record, this is not a certificate: the book is never
released because a verification passed.
"""

import hashlib
from collections.abc import Mapping
from pathlib import Path

from studium.authoring.blueprint import current_sections
from studium.policy.trust import directive_changes_policy
from studium.storage.init_project import load_state_holding_lock
from studium.storage.locking import ProjectLocked, project_lock
from studium.storage.migrate import utc_now
from studium.storage.records import VERIFICATIONS, allocate_id, append_jsonl, fold_by_id
from studium.verification import (
    VerificationStatus,
    verify_algebraic_equivalence,
    verify_derivative,
    verify_dimensions,
    verify_equation,
    verify_integral,
    verify_limit,
    verify_numeric_cross_check,
    verify_substitution,
)
from studium.verification.engine import combine

_AUDIT = "audit/audit.jsonl"
_MIN_METHODS_FOR_INDEPENDENT = 2
_MAX_INPUT_STRING = 1000

_ASSIGNMENT_KINDS = frozenset(
    {
        "equivalence",
        "derivative",
        "integral",
        "equation",
        "substitution",
        "limit",
        "dimensions",
        "numeric_cross_check",
        "combined",
    }
)

#: Statuses accepted as a worked numerical problem for a chapter.
WORKED_VERIFICATION_STATUSES = frozenset(
    {
        VerificationStatus.NUMERICALLY_CROSS_CHECKED,
        VerificationStatus.SYMBOLICALLY_VERIFIED,
        VerificationStatus.DIMENSIONALLY_VERIFIED,
        VerificationStatus.INDEPENDENTLY_VERIFIED,
    }
)


def verify_math(
    root: Path,
    *,
    kind: object = None,
    section: object = None,
    actor: dict[str, object] | None = None,
    timeout: object = 5.0,
    **arguments: object,
) -> dict[str, object]:
    """Run one verification, store the record, and return the result."""

    if not isinstance(kind, str) or kind not in _ASSIGNMENT_KINDS:
        return _error("mcp.invalid_input", "kind must be one of the supported checks")
    checked_section, section_error = _section(root, section)
    if section_error is not None:
        return section_error
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not timeout > 0 or timeout > 30:
        return _error("mcp.invalid_input", "timeout must be a positive number of seconds up to 30")
    try:
        result = _run(kind, arguments, timeout=float(timeout))
    except ValueError as exc:
        return _error("mcp.invalid_input", str(exc))
    try:
        with project_lock(root):
            record_id = allocate_id(root, "VRF")
            record: dict[str, object] = {
                "schema_version": "1.0.0",
                "id": record_id,
                "kind": "verification",
                "check": kind,
                "verification_status": result.status.value,
                "method": result.method,
                "detail": result.detail,
                "ok": result.ok,
                "inputs": result.as_dict().get("inputs"),
                "outputs": result.as_dict().get("outputs"),
                "assumptions": list(result.assumptions),
                "limitations": list(result.limitations),
                "methods_used": list(result.methods_used),
                "accepted": result.ok,
                "recorded_at": utc_now(),
            }
            if checked_section is not None:
                record["section"] = checked_section
            record["input_sha256"] = _fingerprint(record)
            append_jsonl(root / VERIFICATIONS, record)
            _audit(root, record=record, actor=actor)
            fresh = load_state_holding_lock(root)
    except ProjectLocked:
        return _error("storage.locked", "project is locked")
    return _body(fresh, record)


def list_verifications(root: Path) -> list[dict[str, object]]:
    """Stored verification records, newest folding over older edits."""

    return [_public(record) for record in fold_by_id(root / VERIFICATIONS)]


def section_has_strong_verification(root: Path, section_id: str) -> bool:
    """True when a section has a verification strong enough to be a worked problem."""

    for record in fold_by_id(root / VERIFICATIONS):
        if record.get("section") != section_id or record.get("accepted") is not True:
            continue
        status = record.get("verification_status")
        try:
            state = VerificationStatus(status) if isinstance(status, str) else None
        except ValueError:
            state = None
        if state in WORKED_VERIFICATION_STATUSES:
            return True
    return False


def _run(kind: str, arguments: dict[str, object], *, timeout: float):
    if kind == "equivalence":
        left = _text(arguments, "left")
        right = _text(arguments, "right")
        return verify_algebraic_equivalence(
            left,
            right,
            symbols=_symbol_set(arguments.get("symbols")),
            assumptions=_assumptions(arguments.get("assumptions")),
            timeout=timeout,
        )
    if kind == "derivative":
        return verify_derivative(
            _text(arguments, "function"),
            _name(arguments, "variable"),
            _text(arguments, "claimed"),
            symbols=_symbol_set(arguments.get("symbols")),
            assumptions=_assumptions(arguments.get("assumptions")),
            timeout=timeout,
        )
    if kind == "integral":
        return verify_integral(
            _text(arguments, "function"),
            _name(arguments, "variable"),
            _text(arguments, "claimed"),
            lower=_optional_text(arguments, "lower"),
            upper=_optional_text(arguments, "upper"),
            symbols=_symbol_set(arguments.get("symbols")),
            timeout=timeout,
        )
    if kind == "equation":
        return verify_equation(
            _text(arguments, "left"),
            _text(arguments, "right"),
            solution=_string_map(arguments.get("solution")),
            symbols=_symbol_set(arguments.get("symbols")),
            timeout=timeout,
        )
    if kind == "substitution":
        return verify_substitution(
            _text(arguments, "expression"),
            values=_float_map(arguments.get("values")),
            claimed=_float(arguments, "claimed"),
            symbols=_symbol_set(arguments.get("symbols")),
        )
    if kind == "limit":
        return verify_limit(
            _text(arguments, "expression"),
            variable=_name(arguments, "variable"),
            point=_text(arguments, "point"),
            claimed=_text(arguments, "claimed"),
            symbols=_symbol_set(arguments.get("symbols")),
            timeout=timeout,
        )
    if kind == "dimensions":
        return verify_dimensions(
            _text(arguments, "expression"),
            _string_map(arguments.get("symbol_units")),
            expected_unit=_optional_text(arguments, "expected_unit"),
        )
    if kind == "numeric_cross_check":
        return verify_numeric_cross_check(
            _text(arguments, "left"),
            _optional_text(arguments, "right"),
            symbols=_symbol_set(arguments.get("symbols")),
            samples=_samples(arguments.get("samples")),
        )
    if kind == "combined":
        entries = arguments.get("entries")
        if not isinstance(entries, list) or not entries:
            raise ValueError("combined needs entries")
        results = []
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("each entry must be an object")
            entry_kind = entry.get("kind")
            if not isinstance(entry_kind, str) or entry_kind not in _ASSIGNMENT_KINDS:
                raise ValueError("each entry needs a supported kind")
            results.append(_run(entry_kind, entry, timeout=timeout))
        return combine(results)
    raise ValueError(f"unsupported kind: {kind!r}")


def _text(arguments: Mapping[str, object], key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > _MAX_INPUT_STRING:
        raise ValueError(f"{key} is required as a bounded string")
    cleaned = value.strip()
    if directive_changes_policy(cleaned):
        raise ValueError(f"{key} changed policy")
    return cleaned


def _optional_text(arguments: Mapping[str, object], key: str) -> str | None:
    value = arguments.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > _MAX_INPUT_STRING:
        raise ValueError(f"{key} is invalid")
    cleaned = value.strip()
    if directive_changes_policy(cleaned):
        raise ValueError(f"{key} changed policy")
    return cleaned


def _name(arguments: Mapping[str, object], key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    cleaned = value.strip()
    if not cleaned.isidentifier() or cleaned.startswith("_"):
        raise ValueError(f"{key} must be a plain identifier")
    return cleaned


def _symbol_set(value: object) -> set[str] | None:
    if value is None:
        return None
    if not isinstance(value, list) or not value:
        return set()
    names: set[str] = set()
    for item in value:
        if not isinstance(item, str) or not item.isidentifier() or item.startswith("_") or len(item) > 64:
            raise ValueError("symbols must be plain identifiers")
        names.add(item)
    return names


def _assumptions(value: object) -> dict[str, tuple[str, ...]] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("assumptions must be an object")
    result: dict[str, tuple[str, ...]] = {}
    for name, flags in value.items():
        if not isinstance(name, str) or not name.isidentifier() or name.startswith("_"):
            raise ValueError("assumption names must be plain identifiers")
        if not isinstance(flags, list) or not flags:
            raise ValueError(f"assumptions for {name} must be a non-empty list")
        allowed = {"positive", "negative", "real", "integer", "nonzero", "nonnegative", "nonpositive"}
        if any(not isinstance(flag, str) or flag not in allowed for flag in flags):
            raise ValueError(f"assumptions for {name} contain an unsupported flag")
        result[name] = tuple(sorted(set(flags)))
    return result


def _string_map(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("expected an object of name to value pairs")
    result: dict[str, str] = {}
    for name, entry in value.items():
        if not isinstance(name, str) or not name.isidentifier() or name.startswith("_"):
            raise ValueError("keys must be plain identifiers")
        if not isinstance(entry, str) or not entry.strip() or len(entry.strip()) > _MAX_INPUT_STRING:
            raise ValueError(f"value for {name} is invalid")
        cleaned = entry.strip()
        if directive_changes_policy(cleaned):
            raise ValueError(f"value for {name} changed policy")
        result[name] = cleaned
    return result


def _float_map(value: object) -> dict[str, float]:
    if not isinstance(value, dict):
        raise ValueError("values must be an object")
    result: dict[str, float] = {}
    for name, entry in value.items():
        if not isinstance(name, str) or not name.isidentifier() or name.startswith("_"):
            raise ValueError("value names must be plain identifiers")
        result[name] = _as_float(name, entry)
    return result


def _float(arguments: Mapping[str, object], key: str) -> float:
    value = arguments.get(key)
    return _as_float(key, value)


def _as_float(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError(f"{name} must be finite")
    if abs(number) > 1e12:
        raise ValueError(f"{name} is outside the accepted range")
    return number


def _samples(value: object) -> list[dict[str, float]] | None:
    if value is None:
        return None
    if not isinstance(value, list) or not value:
        raise ValueError("samples must be a non-empty list")
    points: list[dict[str, float]] = []
    for point in value:
        if not isinstance(point, dict):
            raise ValueError("each sample must be an object")
        points.append(_float_map(point))
    return points


def _section(root: Path, value: object) -> tuple[str | None, dict[str, object] | None]:
    if value is None:
        return None, None
    if not isinstance(value, str) or not value.strip():
        return None, _error("mcp.invalid_input", "section must be a blueprint section id")
    identifier = value.strip()
    known = {section["id"] for section in current_sections(root)}
    if identifier not in known:
        return None, _error("verification.section_unknown", "section is not in the stored blueprint")
    return identifier, None


def _fingerprint(record: dict[str, object]) -> str:
    payload = "\n".join(
        [
            str(record.get("check") or ""),
            str(record.get("verification_status") or ""),
            str(record.get("method") or ""),
            str(record.get("accepted")),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _as_list(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _public(record: dict[str, object]) -> dict[str, object]:
    visible = {
        "id": record.get("id"),
        "kind": "verification",
        "check": record.get("check"),
        "verification_status": record.get("verification_status"),
        "method": record.get("method"),
        "detail": record.get("detail"),
        "accepted": record.get("accepted") is True,
        "ok": record.get("ok") is True,
        "inputs": record.get("inputs"),
        "outputs": record.get("outputs"),
        "assumptions": _as_list(record.get("assumptions")),
        "limitations": _as_list(record.get("limitations")),
        "methods_used": _as_list(record.get("methods_used")),
    }
    if isinstance(record.get("section"), str):
        visible["section"] = record["section"]
    return visible


def _body(state: dict[str, object], record: dict[str, object]) -> dict[str, object]:
    visible = _public(record)
    return {
        "status": "recorded" if visible["accepted"] else "recorded_but_not_accepted",
        "accepted": visible["accepted"],
        "verification": visible,
        "verification_status": visible["verification_status"],
        "local_sources": _local(state),
        "project_state": state.get("state"),
        "released": state.get("state") == "RELEASED",
    }


def _local(state: dict[str, object]) -> dict[str, object]:
    local = state.get("local_sources")
    if isinstance(local, dict):
        return dict(local)
    return {"status": "UNKNOWN", "prompted": False, "source_count": 0}


def _audit(root: Path, *, record: dict[str, object], actor: dict[str, object] | None) -> None:
    digest = hashlib.sha256(str(record.get("input_sha256", "")).encode("utf-8")).hexdigest()
    append_jsonl(
        root / _AUDIT,
        {
            "schema_version": "1.0.0",
            "timestamp": utc_now(),
            "source_id": record.get("id"),
            "operation": "verify_math",
            "origin": None,
            "actor": {"kind": actor.get("kind")} if isinstance(actor, dict) and isinstance(actor.get("kind"), str) else None,
            "previous_hash": None,
            "new_hash": digest,
            "result": record.get("verification_status"),
            "tool": "math_verify",
        },
    )


def _error(code: str, message: str) -> dict[str, object]:
    return {"status": code, "message": message, "accepted": False}
