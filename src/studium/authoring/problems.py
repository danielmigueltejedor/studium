"""Problems on a blueprint section.

A Rust test is checked only after three passing runs. A numeric answer is
``two_witnesses`` only when its two stored excerpts come from different public
sources. That is not verified. The model is not a source, and a model-written
solution is not correct until the check passes.
"""

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path

from studium.authoring.academic_blueprint import academic_concept_ids
from studium.authoring.blueprint import current_sections
from studium.authoring.computation import ComputationError, evaluate
from studium.authoring.excerpts import excerpts_by_id
from studium.authoring.mathematics import MathError, substitution_latex, symbol_names_of, validate_latex
from studium.authoring.support import corroboration_for_excerpts, paragraph_citation_blockers
from studium.policy.trust import contains_directive, directive_changes_policy
from studium.storage.init_project import domain_profile as _domain_profile
from studium.storage.init_project import load_state_holding_lock
from studium.storage.locking import ProjectLocked, project_lock
from studium.storage.migrate import utc_now
from studium.storage.records import PROBLEMS, allocate_id, append_jsonl, fold_by_id

_AUDIT = "audit/audit.jsonl"
_MAX_PROMPT = 20_000
_MAX_SOURCE = 200_000
_TIMEOUT = 30
_RUNS = 3
_FORBIDDEN_CHARS = set(";|&$`\n\r")
_FORBIDDEN_FLAGS = frozenset({"-L", "--extern", "--sysroot", "--config", "-Z"})
_RUST_TEST = re.compile(r"#\s*\[\s*test\s*\]|\bassert_eq\s*!|\bassert_ne\s*!|\bassert\s*!")
_NO_TEST = (
    "The Rust source has no test. A file of only comments stays unchecked. "
    "It is checked only when the source has a #[test] function or an assert, assert_eq, or assert_ne. "
    "Three runs of an empty file do not count."
)
REPRODUCIBILITY_TEXT = (
    "Three identical rustc runs are a reproducibility check, not an independent proof."
)
RUST_NOT_WORKED_PROBLEM = (
    "A Rust test cannot be the worked problem of a book that is not COMPUTER_SCIENCE."
)
PROBLEM_ROLES = frozenset({"worked", "practice"})
EXERCISE_DIFFICULTIES = frozenset({"FOUNDATIONAL", "INTERMEDIATE", "ADVANCED", "EXAM_LEVEL", "CHALLENGE"})
DIFFICULTY_LEVELS = {
    "FOUNDATIONAL": 1,
    "INTERMEDIATE": 2,
    "ADVANCED": 3,
    "EXAM_LEVEL": 4,
    "CHALLENGE": 5,
}
#: The kind of reasoning a problem exercises. The set is shared by the
#: authoring tool and the renderer so a chapter can be audited for variety.
PROBLEM_TYPES = frozenset(
    {
        "CONCEPTUAL",
        "NUMERICAL",
        "SYMBOLIC",
        "PROOF",
        "DIMENSIONAL",
        "MULTI_STEP",
        "DESIGN",
        "PARAMETER_STUDY",
        "OPTIMIZATION",
        "INTERPRETATION",
        "ERROR_IDENTIFICATION",
        "ASSUMPTION_VALIDATION",
        "APPLICATION",
        "COMPARATIVE",
    }
)
_MAX_OBJECTIVES = 20
_MAX_METHOD = 500
_MAX_SOLUTION_TEXT = 20_000
_MAX_STEPS = 40


def record_problem(
    root: Path,
    *,
    section: object,
    prompt: object,
    source_text: object = None,
    invocation: object = None,
    expected: object = None,
    excerpts: object = None,
    role: object = None,
    difficulty: object = None,
    problem_type: object = None,
    learning_objectives: object = None,
    method: object = None,
    solution: object = None,
    actor: dict[str, object] | None = None,
) -> dict[str, object]:
    """Store one problem. Does not run it and does not change project state."""

    section_id, section_error = _section(root, section)
    if section_error is not None:
        return section_error
    cleaned_prompt, prompt_error = _prompt(prompt)
    if prompt_error is not None:
        return prompt_error
    rust, numeric, mode_error = _mode(source_text, invocation, expected, excerpts)
    if mode_error is not None:
        return mode_error
    problem_role, role_error = _role(role)
    if role_error is not None:
        return role_error
    difficulty_key, difficulty_error = _difficulty(difficulty)
    if difficulty_error is not None:
        return difficulty_error
    type_key, type_error = _problem_type(problem_type)
    if type_error is not None:
        return type_error
    objectives, objectives_error = _objectives(root, learning_objectives)
    if objectives_error is not None:
        return objectives_error
    method_text, method_error = _method(method)
    if method_error is not None:
        return method_error
    solution_value, solution_error = _solution(solution)
    if solution_error is not None:
        return solution_error
    if solution_value is not None and numeric is None:
        return _error("mcp.invalid_input", "a structured solution needs a numeric problem")
    assert section_id is not None and cleaned_prompt is not None
    if directive_changes_policy(cleaned_prompt):
        return _error("policy.overridden", "problem prompt changed policy")
    rust_source: str | None = None
    rust_invocation: list[str] | None = None
    if rust is not None:
        raw_source = rust.get("source_text")
        raw_invocation = rust.get("invocation")
        if not isinstance(raw_source, str) or not isinstance(raw_invocation, list):
            return _error("mcp.invalid_input", "a Rust test needs source_text and an invocation list")
        rust_source = raw_source
        rust_invocation = raw_invocation
        if directive_changes_policy(rust_source):
            return _error("policy.overridden", "problem source changed policy")
    numeric_excerpts: list[str] = []
    if numeric is not None:
        raw_excerpts = numeric.get("excerpts")
        if not isinstance(raw_excerpts, list):
            return _error("mcp.invalid_input", "a numeric problem needs two stored excerpt ids")
        numeric_excerpts = [str(item) for item in raw_excerpts]
        blockers = paragraph_citation_blockers(root, numeric_excerpts)
        if blockers:
            return _rejected(root, blockers)
    try:
        with project_lock(root):
            state = load_state_holding_lock(root)
            if numeric is not None:
                fresh = paragraph_citation_blockers(root, numeric_excerpts)
                if fresh:
                    return _rejected_state(state, fresh)
            identifier = allocate_id(root, "PRB")
            record: dict[str, object] = {
                "schema_version": "1.0.0",
                "id": identifier,
                "section": section_id,
                "prompt": cleaned_prompt,
                "status": "unchecked",
                "classification": "PENDING",
                "correct": False,
                "content_directives_ignored": contains_directive(cleaned_prompt.encode("utf-8")),
                "recorded_at": utc_now(),
            }
            if problem_role is not None:
                record["role"] = problem_role
            if difficulty_key is not None:
                record["difficulty"] = difficulty_key
            if type_key is not None:
                record["problem_type"] = type_key
            if objectives:
                record["learning_objectives"] = objectives
            if method_text is not None:
                record["method"] = method_text
            if solution_value is not None:
                record["solution"] = solution_value
            if rust is not None:
                relative = f"problems/{identifier}/main.rs"
                assert rust_source is not None and rust_invocation is not None
                command, command_error = _command(root, identifier, rust_invocation, relative)
                if command_error is not None:
                    return command_error
                record["kind"] = "rust"
                record["source_text"] = rust_source
                record["source_path"] = relative
                record["invocation"] = command
                record["runs"] = []
                record["status_text"] = _rust_status_text(root)
                _write_source(root, relative, rust_source)
            else:
                assert numeric is not None
                record["kind"] = "numeric"
                record["expected"] = numeric["expected"]
                record["excerpts"] = numeric_excerpts
                if corroboration_for_excerpts(root, numeric_excerpts) == "two_witnesses":
                    record["status"] = "two_witnesses"
                    record["corroboration"] = "two_witnesses"
            _stamp_inputs(root, record)
            append_jsonl(root / PROBLEMS, record)
            _audit(root, record=record, actor=actor, operation="record_problem")
            fresh_state = load_state_holding_lock(root)
            return _body(fresh_state, record, status="recorded")
    except ProjectLocked:
        return _error("storage.locked", "project is locked")


def list_problems(root: Path) -> dict[str, object]:
    """List stored problems. Text is untrusted data. Nothing here is verified."""

    return {"status": "ok", "problems": [_public(record, root) for record in fold_by_id(root / PROBLEMS)]}


def check_problem(root: Path, problem_id: object) -> dict[str, object]:
    """Run a Rust test three times, or report two_witnesses for a numeric problem.

    A missing compiler does not count as a pass. This does not release the book.
    """

    identifier = _identifier(problem_id)
    if identifier is None:
        return _error("mcp.invalid_input", "id is required")
    current = _find(root, identifier)
    if current is None:
        return _error("problem.not_found", "no stored problem with that id")
    if current.get("kind") == "numeric":
        return _check_numeric(root, current)
    if current.get("kind") != "rust":
        return _error("problem.kind_unknown", "problem is not a rust test or a numeric answer")
    return _check_rust(root, current)


def remove_problem(
    root: Path,
    problem_id: object,
    *,
    actor: dict[str, object] | None = None,
) -> dict[str, object]:
    """Delete one stored problem. Sources and paragraphs stay.

    A missing id is an error. This does not change project state and does not
    release the book.
    """

    identifier = _identifier(problem_id)
    if identifier is None:
        return _error("mcp.invalid_input", "id is required")
    current = _find(root, identifier)
    if current is None:
        return _error("problem.not_found", "no stored problem with that id")
    try:
        with project_lock(root):
            again = _find(root, identifier)
            if again is None:
                return _error("problem.not_found", "no stored problem with that id")
            append_jsonl(
                root / PROBLEMS,
                {
                    "schema_version": "1.0.0",
                    "id": identifier,
                    "deleted": True,
                    "recorded_at": utc_now(),
                },
            )
            _audit(root, record=again, actor=actor, operation="remove_problem")
            fresh = load_state_holding_lock(root)
    except ProjectLocked:
        return _error("storage.locked", "project is locked")
    return {
        "status": "removed",
        "problem_id": identifier,
        "message": "The problem is removed from the book. Sources and paragraphs are unchanged.",
        "released": fresh.get("state") == "RELEASED",
        "applied": False,
        "project_state": fresh.get("state"),
        "local_sources": _local(fresh),
    }


def _check_numeric(root: Path, record: dict[str, object]) -> dict[str, object]:
    excerpts = record.get("excerpts")
    stored = excerpts_by_id(root)
    excerpt_ids = list(excerpts) if isinstance(excerpts, list) and all(isinstance(item, str) for item in excerpts) else []
    present = len(excerpt_ids) == 2 and all(item in stored for item in excerpt_ids)
    independent = present and corroboration_for_excerpts(root, excerpt_ids) == "two_witnesses"
    step_checks = _step_checks(record)
    updated = dict(record)
    updated["status"] = "two_witnesses" if independent else "unchecked"
    updated["correct"] = False
    updated["classification"] = "PENDING"
    if step_checks:
        updated["step_checks"] = step_checks
    if independent:
        updated["corroboration"] = "two_witnesses"
    else:
        updated.pop("corroboration", None)
    _stamp_inputs(root, updated)
    if updated != record:
        try:
            with project_lock(root):
                append_jsonl(root / PROBLEMS, updated)
        except ProjectLocked:
            return _error("storage.locked", "project is locked")
    state = _read_state(root)
    body = _body(state, updated, status="two_witnesses" if independent else "unchecked")
    body["checked"] = False
    if step_checks:
        body["step_checks"] = step_checks
        body["steps_reproduced"] = all(check.get("reproduced") is True for check in step_checks)
    return body


def _decimal(value: "Fraction") -> str:
    if value.denominator == 1:
        return str(value.numerator)
    return f"{float(value):.6g}"


def _step_checks(record: dict[str, object]) -> list[dict[str, object]]:
    """Replay every numeric solution step that carries an expression.

    A reproduced step is a calculation that matched its stored result. It is not
    a proof and it does not make the whole solution correct.
    """

    solution = record.get("solution")
    if not isinstance(solution, dict):
        return []
    steps = solution.get("steps")
    if not isinstance(steps, list):
        return []
    checks: list[dict[str, object]] = []
    for index, step in enumerate(steps):
        if not isinstance(step, dict) or "expression" not in step:
            continue
        expression = step["expression"]
        if not isinstance(expression, str):
            continue
        try:
            actual = evaluate(expression)
        except ComputationError as exc:
            checks.append({"index": index, "expression": expression, "reproduced": False, "error": str(exc)})
            continue
        entry: dict[str, object] = {"index": index, "expression": expression, "value": _decimal(actual)}
        if "expected" in step:
            expected = _number(step["expected"])
            entry["expected"] = step["expected"]
            entry["reproduced"] = expected is not None and math.isclose(
                float(expected), float(actual), rel_tol=1e-9, abs_tol=1e-12
            )
        checks.append(entry)
    return checks


def _check_rust(root: Path, record: dict[str, object]) -> dict[str, object]:
    invocation = record.get("invocation")
    source_path = record.get("source_path")
    source_text = record.get("source_text")
    if not isinstance(invocation, list) or not invocation or not isinstance(source_path, str):
        return _error("problem.invocation_invalid", "the stored Rust invocation is not usable")
    if not isinstance(source_text, str):
        return _error("problem.invocation_invalid", "the stored Rust source is missing")
    if not _has_real_rust_test(source_text):
        return _refuse_empty_rust(root, record, _NO_TEST)
    tool = invocation[0] if isinstance(invocation[0], str) else ""
    compiler = shutil.which(tool)
    state = _read_state(root)
    if compiler is None:
        unchecked = dict(record)
        unchecked["status"] = "unchecked"
        unchecked["correct"] = False
        return {
            "status": "compiler_missing",
            "message": f"no {tool} on PATH. The test was not run and is not checked.",
            "checked": False,
            "runs": [],
            "problem": _public(unchecked),
            "local_sources": _local(state),
            "project_state": state.get("state"),
            "released": state.get("state") == "RELEASED",
        }
    try:
        _write_source(root, source_path, source_text)
    except OSError:
        return _error("problem.write_failed", "the test file could not be written inside the book")
    command, command_error = _command(root, str(record.get("id")), [str(item) for item in invocation], source_path)
    if command_error is not None:
        return command_error
    assert command is not None
    runs = _three_runs(root, command, compiler)
    checked = len(runs) == _RUNS and all(run.get("passed") is True for run in runs)
    updated = dict(record)
    updated["invocation"] = command
    updated["runs"] = runs
    updated["status"] = "checked" if checked else "unchecked"
    updated["correct"] = checked
    updated["classification"] = "PENDING"
    updated["checked_at"] = utc_now()
    updated["status_text"] = _rust_status_text(root)
    updated["check_kind"] = "reproducibility" if checked else None
    _stamp_inputs(root, updated)
    try:
        with project_lock(root):
            append_jsonl(root / PROBLEMS, updated)
            _audit(root, record=updated, actor={"kind": "mcp"}, operation="check_problem")
            fresh = load_state_holding_lock(root)
    except ProjectLocked:
        return _error("storage.locked", "project is locked")
    body = _body(fresh, updated, status="checked" if checked else "unchecked")
    body["checked"] = checked
    body["runs"] = runs
    body["message"] = str(updated["status_text"])
    return body


def _has_real_rust_test(source: str) -> bool:
    """True when the source has a #[test] function or an assert outside comments."""

    return _RUST_TEST.search(_rust_code(source)) is not None


def _rust_code(source: str) -> str:
    """Drop comments and string contents so a commented assert is not a test."""

    kept: list[str] = []
    index = 0
    length = len(source)
    while index < length:
        if source.startswith("//", index):
            newline = source.find("\n", index)
            if newline < 0:
                break
            kept.append("\n")
            index = newline + 1
            continue
        if source.startswith("/*", index):
            end = source.find("*/", index + 2)
            kept.append(" ")
            index = length if end < 0 else end + 2
            continue
        if source[index] == '"':
            index += 1
            while index < length:
                if source[index] == "\\" and index + 1 < length:
                    index += 2
                    continue
                if source[index] == '"':
                    index += 1
                    break
                index += 1
            kept.append('""')
            continue
        kept.append(source[index])
        index += 1
    return "".join(kept)


def _refuse_empty_rust(root: Path, record: dict[str, object], message: str) -> dict[str, object]:
    """A compile of comments is not three passing runs and is not checked."""

    updated = dict(record)
    updated["status"] = "unchecked"
    updated["correct"] = False
    updated["classification"] = "PENDING"
    updated["runs"] = []
    updated["checked_at"] = utc_now()
    _stamp_inputs(root, updated)
    try:
        with project_lock(root):
            append_jsonl(root / PROBLEMS, updated)
            _audit(root, record=updated, actor={"kind": "mcp"}, operation="check_problem")
            fresh = load_state_holding_lock(root)
    except ProjectLocked:
        return _error("storage.locked", "project is locked")
    body = _body(fresh, updated, status="unchecked")
    body["checked"] = False
    body["runs"] = []
    body["message"] = message
    return body


def _three_runs(root: Path, command: list[str], compiler: str) -> list[dict[str, object]]:
    """Compile if needed, then run the test three times. A failed compile is not a pass."""

    binary = _output_binary(root, command)
    if command[0] == "rustc":
        compiled = _execute(root, [compiler, *command[1:]])
        if compiled != 0 or binary is None:
            return [
                {"n": 1, "passed": False, "stage": "compile", "exit_code": compiled},
            ]
        runs: list[dict[str, object]] = []
        for number in range(1, _RUNS + 1):
            code = _execute(root, [str(binary)])
            runs.append({"n": number, "passed": code == 0, "exit_code": code})
        return runs
    runs = []
    for number in range(1, _RUNS + 1):
        code = _execute(root, [compiler, *command[1:]])
        runs.append({"n": number, "passed": code == 0, "exit_code": code})
    return runs


def _execute(root: Path, argv: list[str]) -> int:
    env = os.environ.copy()
    env["CARGO_NET_OFFLINE"] = "true"
    for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy"):
        env.pop(key, None)
    try:
        completed = subprocess.run(
            argv,
            cwd=root,
            timeout=_TIMEOUT,
            capture_output=True,
            shell=False,
            env=env,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 1
    return int(completed.returncode)


def _output_binary(root: Path, command: list[str]) -> Path | None:
    if "-o" not in command:
        return None
    index = command.index("-o")
    if index + 1 >= len(command):
        return None
    return _inside(root, command[index + 1])


def _command(
    root: Path,
    identifier: str,
    invocation: list[str],
    source_path: str,
) -> tuple[list[str] | None, dict[str, object] | None]:
    if not invocation or invocation[0] not in {"rustc", "cargo"}:
        return None, _error("problem.invocation_invalid", "invocation must start with rustc or cargo")
    if invocation[0] == "cargo" and (len(invocation) < 2 or invocation[1] != "test"):
        return None, _error("problem.invocation_invalid", "cargo may only run cargo test")
    cleaned: list[str] = [invocation[0]]
    previous_flag = ""
    output_path = f"problems/{identifier}/tester"
    for arg in invocation[1:]:
        if not isinstance(arg, str) or not arg or any(character in _FORBIDDEN_CHARS for character in arg):
            return None, _error("problem.invocation_invalid", "invocation contains a forbidden character")
        if arg in _FORBIDDEN_FLAGS or arg.split("=", 1)[0] in _FORBIDDEN_FLAGS:
            return None, _error("problem.invocation_invalid", "invocation uses a flag that can leave the book")
        if arg.startswith(("http://", "https://")):
            return None, _error("problem.invocation_invalid", "invocation must not fetch a URL")
        rewritten = arg
        if arg in {"main.rs"} or arg.endswith("/main.rs"):
            rewritten = source_path
        elif previous_flag == "-o" and "/" not in arg:
            rewritten = output_path
        if (
            previous_flag in {"-o", "--out-dir", "--manifest-path"} or "/" in rewritten or rewritten.endswith((".rs", ".toml"))
        ) and _inside(root, rewritten) is None:
            return None, _error("problem.invocation_invalid", "invocation path leaves the book")
        cleaned.append(rewritten)
        previous_flag = arg if arg.startswith("-") else ""
    if invocation[0] == "rustc":
        if "--test" not in cleaned:
            cleaned.append("--test")
        if source_path not in cleaned:
            cleaned.append(source_path)
        if "-o" not in cleaned:
            cleaned.extend(["-o", output_path])
        if _output_binary(root, cleaned) is None:
            return None, _error("problem.invocation_invalid", "rustc -o must stay inside the book")
    if invocation[0] == "cargo" and "--offline" not in cleaned:
        cleaned.insert(2, "--offline")
    return cleaned, None


def _inside(root: Path, raw: str) -> Path | None:
    if not raw or raw.startswith("-") or ".." in Path(raw).parts:
        return None
    candidate = Path(raw)
    if candidate.is_absolute():
        return None
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        return None
    return resolved


def _write_source(root: Path, relative: str, text: str) -> None:
    path = _inside(root, relative)
    if path is None:
        raise OSError("path leaves the book")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _mode(
    source_text: object,
    invocation: object,
    expected: object,
    excerpts: object,
) -> tuple[dict[str, object] | None, dict[str, object] | None, dict[str, object] | None]:
    rust_bits = source_text is not None or invocation is not None
    numeric_bits = expected is not None or excerpts is not None
    if rust_bits and numeric_bits:
        return None, None, _error("mcp.invalid_input", "a problem is a Rust test or a numeric answer, not both")
    if rust_bits:
        if not isinstance(source_text, str) or not source_text.strip() or len(source_text) > _MAX_SOURCE:
            return None, None, _error("mcp.invalid_input", "source_text is required for a Rust test")
        command, error = _invocation(invocation)
        if error is not None:
            return None, None, error
        assert command is not None
        return {"source_text": source_text, "invocation": command}, None, None
    if not numeric_bits:
        return None, None, _error("mcp.invalid_input", "a problem needs a Rust test or a numeric answer")
    number = _expected(expected)
    if number is None:
        return None, None, _error("mcp.invalid_input", "expected must be a numeric answer")
    excerpt_ids, excerpt_error = _two_excerpts(excerpts)
    if excerpt_error is not None:
        return None, None, excerpt_error
    return None, {"expected": number, "excerpts": excerpt_ids}, None


def _invocation(value: object) -> tuple[list[str] | None, dict[str, object] | None]:
    if not isinstance(value, list) or not value or len(value) > 40:
        return None, _error("mcp.invalid_input", "invocation must be a rustc or cargo test argument list")
    if not all(isinstance(item, str) and item.strip() for item in value):
        return None, _error("mcp.invalid_input", "invocation must be a rustc or cargo test argument list")
    return [item.strip() for item in value], None


def _expected(value: object) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned and len(cleaned) <= 80:
            try:
                float(cleaned)
            except ValueError:
                return None
            return cleaned
    return None


def _two_excerpts(value: object) -> tuple[list[str] | None, dict[str, object] | None]:
    if not isinstance(value, list) or len(value) != 2:
        return None, _error("mcp.invalid_input", "a numeric problem needs two stored excerpt ids")
    identifiers: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item.strip()) > 128:
            return None, _error("mcp.invalid_input", "a numeric problem needs two stored excerpt ids")
        cleaned = item.strip()
        if cleaned in identifiers:
            return None, _error("mcp.invalid_input", "excerpts lists the same id more than once")
        identifiers.append(cleaned)
    return identifiers, None


def _rust_status_text(root: Path) -> str:
    """Three identical runs are one reproducibility check, not three methods."""

    if _domain_profile(root) == "COMPUTER_SCIENCE":
        return REPRODUCIBILITY_TEXT
    return f"{RUST_NOT_WORKED_PROBLEM} {REPRODUCIBILITY_TEXT}"


def problem_input_sha256(root: Path, record: dict[str, object]) -> str:
    """Fingerprint of the inputs a stored result depends on."""

    parts = [
        str(record.get("prompt") or ""),
        str(record.get("expected") or ""),
        str(record.get("source_text") or ""),
    ]
    solution = record.get("solution")
    if solution:
        parts.append(json.dumps(solution, sort_keys=True, ensure_ascii=False))
    stored = excerpts_by_id(root)
    raw_value = record.get("excerpts")
    raw = raw_value if isinstance(raw_value, list) else []
    for excerpt_id in raw:
        if not isinstance(excerpt_id, str):
            continue
        excerpt = stored.get(excerpt_id)
        digest = excerpt.get("text_sha256") if isinstance(excerpt, dict) else ""
        parts.append(f"{excerpt_id}:{digest}")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def problem_result_current(root: Path, record: dict[str, object]) -> bool:
    """False when a stored result no longer matches the exercise or its excerpts.

    Records written before this fingerprint existed still load.
    """

    stored = record.get("input_sha256")
    if not isinstance(stored, str):
        return True
    return stored == problem_input_sha256(root, record)


def _stamp_inputs(root: Path, record: dict[str, object]) -> None:
    record["input_sha256"] = problem_input_sha256(root, record)


def _public(record: dict[str, object], root: Path | None = None) -> dict[str, object]:
    visible = {
        "id": record.get("id"),
        "section": record.get("section"),
        "prompt": record.get("prompt"),
        "kind": record.get("kind"),
        "status": record.get("status"),
        "classification": "PENDING",
        "correct": record.get("correct") is True,
    }
    if record.get("role") in PROBLEM_ROLES:
        visible["role"] = record["role"]
    if record.get("difficulty") in EXERCISE_DIFFICULTIES:
        visible["difficulty"] = record["difficulty"]
    objectives = record.get("learning_objectives")
    if isinstance(objectives, list):
        visible["learning_objectives"] = [str(item) for item in objectives if isinstance(item, str)]
    if isinstance(record.get("method"), str):
        visible["method"] = record["method"]
    if record.get("problem_type") in PROBLEM_TYPES:
        visible["problem_type"] = record["problem_type"]
    solution = record.get("solution")
    if isinstance(solution, dict):
        visible["solution"] = solution
    if isinstance(record.get("step_checks"), list):
        visible["step_checks"] = record["step_checks"]
    if record.get("kind") == "rust":
        visible["source_path"] = record.get("source_path")
        visible["invocation"] = record.get("invocation")
        visible["runs"] = record.get("runs") if isinstance(record.get("runs"), list) else []
        if isinstance(record.get("status_text"), str):
            visible["status_text"] = record["status_text"]
        if record.get("check_kind") == "reproducibility":
            visible["check_kind"] = "reproducibility"
    if record.get("kind") == "numeric":
        visible["expected"] = record.get("expected")
        visible["excerpts"] = record.get("excerpts")
        visible["status"] = "two_witnesses" if record.get("status") == "two_witnesses" else record.get("status")
        if record.get("corroboration") == "two_witnesses" and visible["status"] == "two_witnesses":
            visible["corroboration"] = "two_witnesses"
    if root is not None and not problem_result_current(root, record):
        visible["status"] = "stale"
        visible["correct"] = False
        visible.pop("corroboration", None)
        visible["current"] = False
    return visible


def _body(state: dict[str, object], record: dict[str, object], *, status: str) -> dict[str, object]:
    return {
        "status": status,
        "problem": _public(record),
        "local_sources": _local(state),
        "project_state": state.get("state"),
        "released": state.get("state") == "RELEASED",
    }


def _find(root: Path, identifier: str) -> dict[str, object] | None:
    return next((item for item in fold_by_id(root / PROBLEMS) if item.get("id") == identifier), None)


def _section(root: Path, value: object) -> tuple[str | None, dict[str, object] | None]:
    if not isinstance(value, str) or not value.strip():
        return None, _error("mcp.invalid_input", "section must be a blueprint section id")
    identifier = value.strip()
    known = {section["id"] for section in current_sections(root)}
    if identifier not in known:
        return None, _error("problem.section_unknown", "section is not in the stored blueprint")
    return identifier, None


def _prompt(value: object) -> tuple[str | None, dict[str, object] | None]:
    if not isinstance(value, str):
        return None, _error("mcp.invalid_input", "prompt is required")
    cleaned = value.strip()
    if not cleaned or len(cleaned) > _MAX_PROMPT:
        return None, _error("mcp.invalid_input", "prompt is required")
    return cleaned, None


def _identifier(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or len(cleaned) > 128:
        return None
    return cleaned


def _role(value: object) -> tuple[str | None, dict[str, object] | None]:
    if value is None:
        return None, None
    if not isinstance(value, str):
        return None, _error("mcp.invalid_input", "role must be worked or practice")
    cleaned = value.strip().lower()
    if cleaned not in PROBLEM_ROLES:
        return None, _error("mcp.invalid_input", "role must be worked or practice")
    return cleaned, None


def _difficulty(value: object) -> tuple[str | None, dict[str, object] | None]:
    if value is None:
        return None, None
    if not isinstance(value, str):
        return None, _error("mcp.invalid_input", _DIFFICULTY_TEXT)
    cleaned = value.strip().upper()
    if cleaned not in EXERCISE_DIFFICULTIES:
        return None, _error("mcp.invalid_input", _DIFFICULTY_TEXT)
    return cleaned, None


_DIFFICULTY_TEXT = "difficulty must be FOUNDATIONAL, INTERMEDIATE, ADVANCED, EXAM_LEVEL, or CHALLENGE"


def _problem_type(value: object) -> tuple[str | None, dict[str, object] | None]:
    if value is None:
        return None, None
    if not isinstance(value, str) or value.strip().upper() not in PROBLEM_TYPES:
        return None, _error("mcp.invalid_input", "problem_type is not a known problem type")
    return value.strip().upper(), None


def _objectives(root: Path, value: object) -> tuple[list[str] | None, dict[str, object] | None]:
    if value is None:
        return [], None
    if not isinstance(value, list) or len(value) > _MAX_OBJECTIVES:
        return None, _error("mcp.invalid_input", "learning_objectives must be academic blueprint concept ids")
    concept_ids = academic_concept_ids(root)
    identifiers: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item.strip()) > 128:
            return None, _error("mcp.invalid_input", "learning_objectives must be academic blueprint concept ids")
        cleaned = item.strip()
        if cleaned not in concept_ids:
            return None, _error(
                "problem.objective_unknown",
                "the learning objective is not a concept of the academic blueprint",
            )
        if cleaned not in identifiers:
            identifiers.append(cleaned)
    return identifiers, None


def _method(value: object) -> tuple[str | None, dict[str, object] | None]:
    if value is None:
        return None, None
    if not isinstance(value, str):
        return None, _error("mcp.invalid_input", "method must be a short sentence")
    cleaned = value.strip()
    if not cleaned or len(cleaned) > _MAX_METHOD:
        return None, _error("mcp.invalid_input", "method must be a short sentence")
    return cleaned, None


def _scalar_text(value: object) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str) and value.strip():
        return value.strip()[:200]
    return None


def _text(value: object, name: str, limit: int = 2_000) -> tuple[str | None, dict[str, object] | None]:
    if value is None:
        return None, None
    if not isinstance(value, str):
        return None, _error("mcp.invalid_input", f"{name} must be text")
    cleaned = value.strip()
    if not cleaned or len(cleaned) > limit:
        return None, _error("mcp.invalid_input", f"{name} must be text")
    return cleaned, None


def _text_list(value: object, name: str, limit: int = _MAX_STEPS) -> tuple[list[str] | None, dict[str, object] | None]:
    if value is None:
        return [], None
    if not isinstance(value, list) or len(value) > limit:
        return None, _error("mcp.invalid_input", f"{name} must be a short list of texts")
    items: list[str] = []
    for entry in value:
        text, error = _text(entry, name)
        if error is not None:
            return None, error
        assert text is not None
        items.append(text)
    return items, None


def _latex_field(value: object, name: str) -> tuple[str | None, dict[str, object] | None]:
    if value is None:
        return None, None
    if not isinstance(value, str) or not value.strip():
        return None, _error("mcp.invalid_input", f"{name} must be a non-empty LaTeX fragment")
    cleaned = value.strip()
    problems = validate_latex(cleaned)
    if problems:
        return None, _error("mcp.invalid_input", f"{name} is not valid LaTeX: " + "; ".join(problems))
    return cleaned, None


def _given(value: object) -> tuple[list[dict[str, str]] | None, dict[str, object] | None]:
    if value is None:
        return [], None
    if not isinstance(value, list) or len(value) > _MAX_STEPS:
        return None, _error("mcp.invalid_input", "solution.given must be a list of quantities")
    quantities: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            return None, _error("mcp.invalid_input", "each given quantity must be an object")
        symbol = item.get("symbol")
        number = _scalar_text(item.get("value"))
        unit, unit_error = _text(item.get("unit"), "solution.given.unit", 100)
        if unit_error is not None:
            return None, unit_error
        if not isinstance(symbol, str) or not symbol.strip().isidentifier():
            return None, _error("mcp.invalid_input", "a given symbol must be an identifier")
        symbol = symbol.strip()
        if symbol in seen:
            return None, _error("mcp.invalid_input", "a given symbol is repeated")
        if number is None or unit is None:
            return None, _error("mcp.invalid_input", "a given quantity needs a value and a unit")
        seen.add(symbol)
        entry = {"symbol": symbol, "value": number, "unit": unit}
        meaning, meaning_error = _text(item.get("meaning"), "solution.given.meaning", 300)
        if meaning_error is not None:
            return None, meaning_error
        if meaning is not None:
            entry["meaning"] = meaning
        quantities.append(entry)
    return quantities, None


def _model(value: object) -> tuple[list[dict[str, str]] | None, dict[str, object] | None]:
    if value is None:
        return [], None
    if not isinstance(value, list) or len(value) > _MAX_STEPS:
        return None, _error("mcp.invalid_input", "solution.model must be a list of equations")
    equations: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            return None, _error("mcp.invalid_input", "each model equation must be an object")
        name, name_error = _text(item.get("name"), "solution.model.name", 300)
        latex, latex_error = _latex_field(item.get("latex"), "solution.model.latex")
        if name_error is not None or latex_error is not None or name is None or latex is None:
            return None, name_error or latex_error or _error("mcp.invalid_input", "a model equation needs a name and LaTeX")
        equation = {"name": name, "latex": latex}
        symbolic, symbolic_error = _symbolic_field(item.get("symbolic"), "solution.model.symbolic")
        if symbolic_error is not None:
            return None, symbolic_error
        if symbolic is not None:
            equation["symbolic"] = symbolic
        equations.append(equation)
    return equations, None


def _symbolic_field(value: object, name: str) -> tuple[str | None, dict[str, object] | None]:
    if value is None:
        return None, None
    if not isinstance(value, str) or not value.strip():
        return None, _error("mcp.invalid_input", f"{name} must be a symbolic expression")
    cleaned = value.strip()
    try:
        symbol_names_of(cleaned)
    except MathError as exc:
        return None, _error("mcp.invalid_input", f"{name} is not a valid symbolic expression: {exc}")
    return cleaned, None


def _steps(value: object) -> tuple[list[dict[str, str]] | None, dict[str, object] | None]:
    if value is None:
        return [], None
    if not isinstance(value, list) or len(value) > _MAX_STEPS:
        return None, _error("mcp.invalid_input", "solution.steps must be a short list")
    steps: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            return None, _error("mcp.invalid_input", "each solution step must be an object")
        text, text_error = _text(item.get("text"), "solution.steps.text", 2_000)
        if text_error is not None:
            return None, text_error
        step: dict[str, str] = {}
        if text is not None:
            step["text"] = text
        for field, checker in (("equation", _latex_field), ("symbolic", _symbolic_field)):
            cleaned, field_error = checker(item.get(field), f"solution.steps.{field}")
            if field_error is not None:
                return None, field_error
            if cleaned is not None:
                step[field] = cleaned
        expression = item.get("expression")
        if expression is not None:
            if not isinstance(expression, str) or not expression.strip():
                return None, _error("mcp.invalid_input", "a step expression must be text")
            try:
                evaluate(expression)
            except ComputationError as exc:
                return None, _error("mcp.invalid_input", f"a step expression cannot be checked: {exc}")
            step["expression"] = expression.strip()
        expected = _scalar_text(item.get("expected"))
        if expected is not None:
            step["expected"] = expected
        if "expression" in step and "expected" in step:
            try:
                if _number(step["expected"]) is None:
                    raise ComputationError("expected is not a number")
            except ComputationError as exc:
                return None, _error("mcp.invalid_input", f"a step expected value cannot be compared: {exc}")
        unit, unit_error = _text(item.get("unit"), "solution.steps.unit", 100)
        if unit_error is not None:
            return None, unit_error
        if unit is not None:
            step["unit"] = unit
        if not step:
            return None, _error("mcp.invalid_input", "a solution step needs some content")
        steps.append(step)
    return steps, None


def _number(value: object) -> "Fraction | None":
    from fractions import Fraction

    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Fraction)):
        return Fraction(value)
    if isinstance(value, str):
        try:
            return Fraction(value.strip())
        except (ValueError, ZeroDivisionError):
            return None
    return None


def _auto_substitution(model: list[dict[str, str]], given: list[dict[str, str]]) -> str | None:
    lookup = {entry["symbol"]: (entry["value"], entry["unit"]) for entry in given}
    for equation in model:
        symbolic = equation.get("symbolic")
        if not symbolic:
            continue
        try:
            names = symbol_names_of(symbolic)
        except MathError:
            continue
        if names and all(name in lookup for name in names):
            try:
                return substitution_latex(symbolic, {name: lookup[name] for name in names})
            except MathError:
                return None
    return None


def _solution(value: object) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    """Validate and normalize the optional structured solution of a numeric problem."""

    if value is None:
        return None, None
    if not isinstance(value, dict):
        return None, _error("mcp.invalid_input", "solution must be an object")
    normalized: dict[str, object] = {}
    given, error = _given(value.get("given"))
    if error is not None:
        return None, error
    model, error = _model(value.get("model"))
    if error is not None:
        return None, error
    steps, error = _steps(value.get("steps"))
    if error is not None:
        return None, error
    for name in ("assumptions", "development", "limitations", "mistakes"):
        items, list_error = _text_list(value.get(name), f"solution.{name}")
        if list_error is not None:
            return None, list_error
        if items:
            normalized[name] = items
    for name in ("unknown", "interpretation"):
        text, text_error = _text(value.get(name), f"solution.{name}")
        if text_error is not None:
            return None, text_error
        if text is not None:
            normalized[name] = text
    for name in ("substitution", "result"):
        latex, latex_error = _latex_field(value.get(name), f"solution.{name}")
        if latex_error is not None:
            return None, latex_error
        if latex is not None:
            normalized[name] = latex
    if given:
        normalized["given"] = given
    if model:
        normalized["model"] = model
    if steps:
        normalized["steps"] = steps
    if "substitution" not in normalized and model and given:
        computed = _auto_substitution(model, given)
        if computed is not None:
            normalized["substitution"] = computed
    if not normalized:
        return None, _error("mcp.invalid_input", "solution has no usable field")
    return normalized, None


def _rejected(root: Path, blockers: list[dict[str, object]]) -> dict[str, object]:
    return _rejected_state(_read_state(root), blockers)


def _rejected_state(state: dict[str, object], blockers: list[dict[str, object]]) -> dict[str, object]:
    return {
        "status": "rejected",
        "message": "a problem excerpt cannot support a draft",
        "blockers": blockers,
        "local_sources": _local(state),
        "project_state": state.get("state"),
        "released": state.get("state") == "RELEASED",
    }


def _read_state(root: Path) -> dict[str, object]:
    try:
        with project_lock(root):
            return load_state_holding_lock(root)
    except ProjectLocked:
        return {}


def _audit(root: Path, *, record: dict[str, object], actor: dict[str, object] | None, operation: str) -> None:
    digest = hashlib.sha256(str(record.get("prompt", "")).encode("utf-8")).hexdigest()
    append_jsonl(
        root / _AUDIT,
        {
            "schema_version": "1.0.0",
            "timestamp": utc_now(),
            "source_id": record.get("id"),
            "operation": operation,
            "origin": None,
            "actor": {"kind": actor.get("kind")} if isinstance(actor, dict) and isinstance(actor.get("kind"), str) else None,
            "previous_hash": None,
            "new_hash": digest,
            "result": record.get("status"),
            "tool": operation,
        },
    )


def _local(state: dict[str, object]) -> dict[str, object]:
    local = state.get("local_sources")
    if isinstance(local, dict):
        return dict(local)
    return {"status": "UNKNOWN", "prompted": False, "source_count": 0}


def _error(code: str, message: str) -> dict[str, object]:
    return {"status": code, "message": message}
