"""Problems on a blueprint section.

A Rust test is checked only after three passing runs. A numeric answer with
two stored excerpts is ``two_witnesses``, not verified. The model is not a
source, and a model-written solution is not correct until the check passes.
"""

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

from studium.authoring.blueprint import current_sections
from studium.authoring.excerpts import excerpts_by_id
from studium.authoring.support import paragraph_citation_blockers
from studium.policy.trust import contains_directive, directive_changes_policy
from studium.storage.init_project import load_state_holding_lock
from studium.storage.locking import ProjectLocked, project_lock
from studium.storage.migrate import utc_now
from studium.storage.records import PROBLEMS, allocate_id, append_jsonl, fold_by_id

_AUDIT = "audit/audit.jsonl"
_MAX_PROMPT = 20_000
_MAX_SOURCE = 200_000
_TIMEOUT = 20
_RUNS = 3
_FORBIDDEN_CHARS = set(";|&$`\n\r")
_FORBIDDEN_FLAGS = frozenset({"-L", "--extern", "--sysroot", "--config", "-Z"})


def record_problem(
    root: Path,
    *,
    section: object,
    prompt: object,
    source_text: object = None,
    invocation: object = None,
    expected: object = None,
    excerpts: object = None,
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
    assert section_id is not None and cleaned_prompt is not None
    if directive_changes_policy(cleaned_prompt):
        return _error("policy.overridden", "problem prompt changed policy")
    if rust is not None and directive_changes_policy(rust["source_text"]):
        return _error("policy.overridden", "problem source changed policy")
    if numeric is not None:
        blockers = paragraph_citation_blockers(root, numeric["excerpts"])
        if blockers:
            return _rejected(root, blockers)
    try:
        with project_lock(root):
            state = load_state_holding_lock(root)
            if numeric is not None:
                fresh = paragraph_citation_blockers(root, numeric["excerpts"])
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
            if rust is not None:
                relative = f"problems/{identifier}/main.rs"
                command, command_error = _command(root, identifier, rust["invocation"], relative)
                if command_error is not None:
                    return command_error
                record["kind"] = "rust"
                record["source_text"] = rust["source_text"]
                record["source_path"] = relative
                record["invocation"] = command
                record["runs"] = []
                _write_source(root, relative, rust["source_text"])
            else:
                assert numeric is not None
                record["kind"] = "numeric"
                record["expected"] = numeric["expected"]
                record["excerpts"] = numeric["excerpts"]
                record["status"] = "two_witnesses"
            append_jsonl(root / PROBLEMS, record)
            _audit(root, record=record, actor=actor, operation="record_problem")
            fresh_state = load_state_holding_lock(root)
            return _body(fresh_state, record, status="recorded")
    except ProjectLocked:
        return _error("storage.locked", "project is locked")


def list_problems(root: Path) -> dict[str, object]:
    """List stored problems. Text is untrusted data. Nothing here is verified."""

    return {"status": "ok", "problems": [_public(record) for record in fold_by_id(root / PROBLEMS)]}


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


def _check_numeric(root: Path, record: dict[str, object]) -> dict[str, object]:
    excerpts = record.get("excerpts")
    stored = excerpts_by_id(root)
    present = (
        isinstance(excerpts, list)
        and len(excerpts) == 2
        and all(isinstance(item, str) and item in stored for item in excerpts)
    )
    updated = dict(record)
    updated["status"] = "two_witnesses" if present else "unchecked"
    updated["correct"] = False
    updated["classification"] = "PENDING"
    if updated != record:
        try:
            with project_lock(root):
                append_jsonl(root / PROBLEMS, updated)
        except ProjectLocked:
            return _error("storage.locked", "project is locked")
    state = _read_state(root)
    body = _body(state, updated, status="two_witnesses" if present else "unchecked")
    body["checked"] = False
    return body


def _check_rust(root: Path, record: dict[str, object]) -> dict[str, object]:
    invocation = record.get("invocation")
    source_path = record.get("source_path")
    source_text = record.get("source_text")
    if not isinstance(invocation, list) or not invocation or not isinstance(source_path, str):
        return _error("problem.invocation_invalid", "the stored Rust invocation is not usable")
    if not isinstance(source_text, str):
        return _error("problem.invocation_invalid", "the stored Rust source is missing")
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
    runs = _three_runs(root, command, compiler)
    checked = len(runs) == _RUNS and all(run.get("passed") is True for run in runs)
    updated = dict(record)
    updated["invocation"] = command
    updated["runs"] = runs
    updated["status"] = "checked" if checked else "unchecked"
    updated["correct"] = checked
    updated["classification"] = "PENDING"
    updated["checked_at"] = utc_now()
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
        if previous_flag in {"-o", "--out-dir", "--manifest-path"} or "/" in rewritten or rewritten.endswith((".rs", ".toml")):
            if _inside(root, rewritten) is None:
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
) -> tuple[dict[str, str] | None, dict[str, object] | None, dict[str, object] | None]:
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


def _public(record: dict[str, object]) -> dict[str, object]:
    visible = {
        "id": record.get("id"),
        "section": record.get("section"),
        "prompt": record.get("prompt"),
        "kind": record.get("kind"),
        "status": record.get("status"),
        "classification": "PENDING",
        "correct": record.get("correct") is True,
    }
    if record.get("kind") == "rust":
        visible["source_path"] = record.get("source_path")
        visible["invocation"] = record.get("invocation")
        visible["runs"] = record.get("runs") if isinstance(record.get("runs"), list) else []
    if record.get("kind") == "numeric":
        visible["expected"] = record.get("expected")
        visible["excerpts"] = record.get("excerpts")
        visible["status"] = "two_witnesses" if record.get("status") == "two_witnesses" else record.get("status")
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
