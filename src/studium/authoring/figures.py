"""Figures inside an explanation.

A drawing is checked only when the server runs its stored source again and
the output file exists. The model describing a picture is not a check. A
figure does not prove the science. A numeric claim in the caption still needs
two excerpts or a replayed computation.
"""

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

from studium.authoring.blueprint import current_sections
from studium.authoring.support import corroboration_for_excerpts, paragraph_citation_blockers
from studium.policy.trust import contains_directive, directive_changes_policy
from studium.storage.init_project import load_state_holding_lock
from studium.storage.locking import ProjectLocked, project_lock
from studium.storage.migrate import utc_now
from studium.storage.records import COMPUTATIONS, FIGURES, PROBLEMS, allocate_id, append_jsonl, fold_by_id

_AUDIT = "audit/audit.jsonl"
_MAX_CAPTION = 2_000
_MAX_SOURCE = 100_000
_MAX_EXCERPTS = 40
_TIMEOUT = 20
_KINDS = frozenset({"tikz", "python"})
_PY_FORBIDDEN = (
    "http://",
    "https://",
    "urlopen",
    "urllib",
    "socket",
    "subprocess",
    "ctypes",
    "importlib",
    "os.system",
    "os.popen",
    "os.exec",
    "os.spawn",
    "../",
)
_TIKZ_FORBIDDEN = (
    "\\input",
    "\\include",
    "\\write",
    "\\openout",
    "\\usepackage",
    "\\documentclass",
    "\\immediate",
    "\\catcode",
    "\\end{document}",
    "\\end{tikzpicture}",
    "\\shell",
    "http://",
    "https://",
    "../",
)
_SCIENCE = (
    "A figure does not prove the science. "
    "A numeric claim in the caption needs two excerpts or a replayed computation."
)
_PRELUDE = r"""
import builtins
import io
import os
import pathlib
import socket
import subprocess
import sys

work = pathlib.Path.cwd().resolve()
program = sys.stdin.read()

def _deny(*_args, **_kwargs):
    raise OSError("network is disabled")

for _name in (
    "system", "popen", "execv", "execve", "execl", "execlp", "execvp", "execvpe", "execlpe",
    "spawnv", "spawnve", "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnvp", "spawnvpe",
    "fork", "forkpty", "posix_spawn", "posix_spawnp",
):
    if hasattr(os, _name):
        setattr(os, _name, _deny)
socket.socket = _deny
socket.create_connection = _deny
socket.getaddrinfo = _deny
subprocess.Popen = _deny
subprocess.run = _deny
subprocess.call = _deny
subprocess.check_call = _deny
subprocess.check_output = _deny

def _contained(file):
    path = pathlib.Path(file)
    if not path.is_absolute():
        path = work / path
    resolved = path.resolve()
    try:
        resolved.relative_to(work)
    except ValueError:
        raise OSError("path leaves the book") from None
    return resolved

_io_open = io.open

def _open(file, mode="r", *args, **kwargs):
    if isinstance(file, int):
        raise OSError("path leaves the book")
    return _io_open(_contained(file), mode, *args, **kwargs)

io.open = _open
builtins.open = _open
_os_open = os.open

def _open_os(path, flags, mode=0o777, *, dir_fd=None):
    if dir_fd is not None:
        raise OSError("path leaves the book")
    return _os_open(_contained(path), flags, mode)

os.open = _open_os
_blocked_imports = {
    "_io", "ctypes", "importlib", "multiprocessing", "pty", "pickle", "marshal",
    "runpy", "shutil", "socket", "subprocess",
}
_real_import = builtins.__import__

def _import(name, globals=None, locals=None, fromlist=(), level=0):
    root_name = name.split(".", 1)[0]
    if root_name in _blocked_imports:
        raise ImportError("import is disabled")
    return _real_import(name, globals, locals, fromlist, level)

_compile = builtins.compile
_exec = builtins.exec
builtins.__import__ = _import
builtins.eval = _deny
builtins.exec = _deny
builtins.compile = _deny
builtins.breakpoint = _deny
sys.stdin = _io_open(os.devnull)
code = _compile(program, "plot.py", "exec")
safe_builtins = dict(vars(builtins))
safe_builtins["open"] = _open
safe_builtins["__import__"] = _import
for _banned in ("eval", "exec", "compile", "breakpoint"):
    safe_builtins.pop(_banned, None)
_exec(code, {"__name__": "__main__", "__file__": "plot.py", "__builtins__": safe_builtins})
"""


def figure_gap(identifier: str) -> str:
    """Visible placeholder for a drawing that was not checked.

    The figure id stays out of the chapter. Callers still pass it so the
    gap stays tied to that record in code.
    """

    del identifier
    return "Gap: this figure is unchecked. The drawing is omitted."


def record_figure(
    root: Path,
    *,
    section: object,
    caption: object,
    source: object,
    kind: object,
    excerpts: object,
    actor: dict[str, object] | None = None,
) -> dict[str, object]:
    """Store one figure. Does not run it, fetch a URL, or change project state."""

    section_id, section_error = _section(root, section)
    if section_error is not None:
        return section_error
    cleaned_caption, caption_error = _caption(caption)
    if caption_error is not None:
        return caption_error
    figure_kind, kind_error = _kind(kind)
    if kind_error is not None:
        return kind_error
    cleaned_source, source_error = _source(source, figure_kind)
    if source_error is not None:
        return source_error
    excerpt_ids, excerpt_error = _excerpts(excerpts)
    if excerpt_error is not None:
        return excerpt_error
    assert section_id is not None and cleaned_caption is not None and figure_kind is not None
    assert cleaned_source is not None and excerpt_ids is not None
    if directive_changes_policy(cleaned_caption) or directive_changes_policy(cleaned_source):
        return _error("policy.overridden", "figure text changed policy")
    blockers = paragraph_citation_blockers(root, excerpt_ids)
    if blockers:
        return _rejected(root, blockers)
    try:
        with project_lock(root):
            state = load_state_holding_lock(root)
            fresh = paragraph_citation_blockers(root, excerpt_ids)
            if fresh:
                return _rejected_state(state, fresh)
            identifier = allocate_id(root, "FIG")
            record: dict[str, object] = {
                "schema_version": "1.0.0",
                "id": identifier,
                "section": section_id,
                "caption": cleaned_caption,
                "kind": figure_kind,
                "source": cleaned_source,
                "source_sha256": hashlib.sha256(cleaned_source.encode("utf-8")).hexdigest(),
                "excerpts": excerpt_ids,
                "status": "unchecked",
                "classification": "PENDING",
                "correct": False,
                "proves_science": False,
                "caption_corroboration": _caption_corroboration(root, cleaned_caption, excerpt_ids, section_id),
                "content_directives_ignored": contains_directive(cleaned_caption.encode("utf-8")),
                "recorded_at": utc_now(),
            }
            append_jsonl(root / FIGURES, record)
            _audit(root, record=record, actor=actor, operation="record_figure")
            fresh_state = load_state_holding_lock(root)
            return _body(fresh_state, record, status="recorded", checked=False)
    except ProjectLocked:
        return _error("storage.locked", "project is locked")


def check_figure(root: Path, figure_id: object) -> dict[str, object]:
    """Run the stored source again. A missing engine or a failed run is not checked.

    The stored source is what runs. A description of the drawing is not accepted.
    This does not fetch a URL and does not release the book.
    """

    identifier = _identifier(figure_id)
    if identifier is None:
        return _error("mcp.invalid_input", "id is required")
    current = _find(root, identifier)
    if current is None:
        return _error("figure.not_found", "no stored figure with that id")
    kind = current.get("kind")
    source = current.get("source")
    if kind not in _KINDS or not isinstance(source, str) or not source.strip():
        return _error("figure.source_missing", "a figure needs executable source")
    engine_name = "pdflatex" if kind == "tikz" else "python3"
    engine = shutil.which(engine_name)
    state = _read_state(root)
    if engine is None:
        unchecked = dict(current)
        unchecked["status"] = "unchecked"
        unchecked["correct"] = False
        unchecked["proves_science"] = False
        return {
            "status": "compiler_missing",
            "message": f"no {engine_name} on PATH. The figure was not run and is not checked.",
            "checked": False,
            "figure": _public(unchecked),
            "local_sources": _local(state),
            "project_state": state.get("state"),
            "released": state.get("state") == "RELEASED",
        }
    work = _work_dir(root, identifier)
    if work is None:
        return _error("figure.path_escaped", "figure path leaves the book")
    try:
        work.mkdir(parents=True, exist_ok=True)
        _clear_outputs(work)
        if kind == "tikz":
            code, detail = _run_tikz(engine, work, source)
            output_name = "figure.pdf"
        else:
            code, detail = _run_python(engine, root, work, source)
            output_name = _python_output(work)
    except OSError:
        return _error("figure.write_failed", "the figure source could not be written inside the book")
    output = work / output_name if isinstance(output_name, str) else None
    produced = code == 0 and output is not None and _output_ok(root, output)
    updated = dict(current)
    updated["status"] = "checked" if produced else "unchecked"
    updated["correct"] = produced
    updated["proves_science"] = False
    updated["classification"] = "PENDING"
    updated["checked_at"] = utc_now()
    excerpts_value = updated.get("excerpts")
    excerpts = excerpts_value if isinstance(excerpts_value, list) else []
    excerpt_ids = [item for item in excerpts if isinstance(item, str)]
    caption_value = updated.get("caption")
    section_value = updated.get("section")
    caption = caption_value if isinstance(caption_value, str) else ""
    section_id = section_value if isinstance(section_value, str) else ""
    updated["caption_corroboration"] = _caption_corroboration(root, caption, excerpt_ids, section_id)
    if produced and output is not None:
        updated["output"] = output.resolve().relative_to(root.resolve()).as_posix()
    else:
        updated.pop("output", None)
        _clear_outputs(work)
    try:
        with project_lock(root):
            append_jsonl(root / FIGURES, updated)
            _audit(root, record=updated, actor={"kind": "mcp"}, operation="check_figure")
            fresh = load_state_holding_lock(root)
    except ProjectLocked:
        return _error("storage.locked", "project is locked")
    body = _body(fresh, updated, status="checked" if produced else "unchecked", checked=produced)
    if not produced:
        message = "the figure program failed. The figure is not checked."
        if detail:
            message = f"{message} {detail}"
        body["message"] = message
    return body


def remove_figure(
    root: Path,
    figure_id: object,
    *,
    actor: dict[str, object] | None = None,
) -> dict[str, object]:
    """Delete one stored figure. Sources, paragraphs, and excerpts stay.

    A missing id is an error. This does not change project state and does not
    release the book.
    """

    identifier = _identifier(figure_id)
    if identifier is None:
        return _error("mcp.invalid_input", "id is required")
    current = _find(root, identifier)
    if current is None:
        return _error("figure.not_found", "no stored figure with that id")
    try:
        with project_lock(root):
            again = _find(root, identifier)
            if again is None:
                return _error("figure.not_found", "no stored figure with that id")
            append_jsonl(
                root / FIGURES,
                {
                    "schema_version": "1.0.0",
                    "id": identifier,
                    "deleted": True,
                    "recorded_at": utc_now(),
                },
            )
            _audit(root, record=again, actor=actor, operation="remove_figure")
            fresh = load_state_holding_lock(root)
    except ProjectLocked:
        return _error("storage.locked", "project is locked")
    return {
        "status": "removed",
        "checked": False,
        "figure_id": identifier,
        "message": "The figure is removed from the book. Sources, paragraphs, and excerpts are unchanged.",
        "released": fresh.get("state") == "RELEASED",
        "applied": False,
        "project_state": fresh.get("state"),
        "local_sources": _local(fresh),
    }


def figures_in_section(root: Path, section_id: str) -> list[dict[str, object]]:
    """Stored figures for one blueprint section, newest record per id."""

    return [record for record in fold_by_id(root / FIGURES) if record.get("section") == section_id]


def _run_tikz(engine: str, work: Path, source: str) -> tuple[int, str]:
    tex = work / "figure.tex"
    tex.write_text(_tikz_document(source), encoding="utf-8")
    command = [
        engine,
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-no-shell-escape",
        "--cnf-line=openout_any=p",
        "-jobname=figure",
        "figure.tex",
    ]
    return _execute(command, work)


def _run_python(engine: str, root: Path, work: Path, source: str) -> tuple[int, str]:
    script = work / "plot.py"
    script.write_text(source, encoding="utf-8")
    env = os.environ.copy()
    for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy"):
        env.pop(key, None)
    env["STUDIUM_BOOK"] = str(root.resolve())
    env["HOME"] = str(work)
    env["TMPDIR"] = str(work)
    env["MPLCONFIGDIR"] = str(work)
    env["XDG_CACHE_HOME"] = str(work)
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONSAFEPATH"] = "1"
    return _execute([engine, "-I", "-c", _PRELUDE], work, env=env, stdin=source.encode("utf-8"))


def _execute(
    command: list[str],
    work: Path,
    *,
    env: dict[str, str] | None = None,
    stdin: bytes | None = None,
) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            command,
            cwd=work,
            timeout=_TIMEOUT,
            capture_output=True,
            shell=False,
            env=env,
            input=stdin,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return 1, "the run timed out"
    except OSError as exc:
        return 1, str(exc)[:200]
    if completed.returncode == 0:
        return 0, ""
    tail = completed.stdout.decode("utf-8", errors="replace")[-200:]
    err = completed.stderr.decode("utf-8", errors="replace")[-200:]
    detail = " ".join(f"{tail} {err}".split())
    return int(completed.returncode), detail[:200]


def _tikz_document(source: str) -> str:
    return "\n".join(
        [
            r"\documentclass{article}",
            r"\usepackage{tikz}",
            r"\pagestyle{empty}",
            r"\begin{document}",
            r"\begin{tikzpicture}",
            source,
            r"\end{tikzpicture}",
            r"\end{document}",
            "",
        ]
    )


def _python_output(work: Path) -> str | None:
    for name in ("figure.png", "figure.pdf"):
        if _output_ok(work.parent.parent, work / name):
            return name
    return None


def _output_ok(root: Path, path: Path) -> bool:
    try:
        if path.is_symlink():
            return False
        resolved = path.resolve()
        resolved.relative_to(root.resolve())
        return resolved.is_file() and resolved.stat().st_size > 0
    except (OSError, ValueError):
        return False


def _clear_outputs(work: Path) -> None:
    for name in ("figure.png", "figure.pdf"):
        path = work / name
        try:
            if path.is_symlink() or path.is_file():
                path.unlink()
        except OSError:
            continue


def _work_dir(root: Path, identifier: str) -> Path | None:
    if "/" in identifier or ".." in identifier:
        return None
    candidate = (root / "figures" / identifier).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def _caption_corroboration(root: Path, caption: str, excerpt_ids: list[str], section_id: str) -> str:
    if not any(character.isdigit() for character in caption):
        return "none"
    if corroboration_for_excerpts(root, excerpt_ids) == "two_witnesses":
        return "two_witnesses"
    if _section_has_replay(root, section_id):
        return "replayed"
    return "unchecked"


def _section_has_replay(root: Path, section_id: str) -> bool:
    for record in fold_by_id(root / PROBLEMS):
        if record.get("section") != section_id:
            continue
        if record.get("kind") == "rust" and record.get("status") == "checked" and record.get("correct") is True:
            return True
    for record in fold_by_id(root / COMPUTATIONS):
        if record.get("section") == section_id and record.get("status") == "replayed" and record.get("correct") is True:
            return True
    return False


def _public(record: dict[str, object]) -> dict[str, object]:
    visible = {
        "id": record.get("id"),
        "section": record.get("section"),
        "caption": record.get("caption"),
        "kind": record.get("kind"),
        "excerpts": record.get("excerpts"),
        "status": "checked" if record.get("status") == "checked" and record.get("correct") is True else "unchecked",
        "classification": "PENDING",
        "correct": record.get("correct") is True,
        "proves_science": False,
        "caption_corroboration": record.get("caption_corroboration"),
    }
    if isinstance(record.get("output"), str):
        visible["output"] = record["output"]
    return visible


def _body(state: dict[str, object], record: dict[str, object], *, status: str, checked: bool) -> dict[str, object]:
    return {
        "status": status,
        "checked": checked,
        "message": _SCIENCE,
        "figure": _public(record),
        "local_sources": _local(state),
        "project_state": state.get("state"),
        "released": state.get("state") == "RELEASED",
    }


def _find(root: Path, identifier: str) -> dict[str, object] | None:
    return next((item for item in fold_by_id(root / FIGURES) if item.get("id") == identifier), None)


def _section(root: Path, value: object) -> tuple[str | None, dict[str, object] | None]:
    if not isinstance(value, str) or not value.strip():
        return None, _error("mcp.invalid_input", "section must be a blueprint section id")
    identifier = value.strip()
    known = {section["id"] for section in current_sections(root)}
    if identifier not in known:
        return None, _error("figure.section_unknown", "section is not in the stored blueprint")
    return identifier, None


def _caption(value: object) -> tuple[str | None, dict[str, object] | None]:
    if not isinstance(value, str):
        return None, _error("mcp.invalid_input", "caption is required")
    cleaned = value.strip()
    if not cleaned or len(cleaned) > _MAX_CAPTION:
        return None, _error("mcp.invalid_input", "caption is required")
    return cleaned, None


def _kind(value: object) -> tuple[str | None, dict[str, object] | None]:
    if not isinstance(value, str) or value.strip().lower() not in _KINDS:
        return None, _error("mcp.invalid_input", "kind must be tikz or python")
    return value.strip().lower(), None


def _source(value: object, kind: str | None) -> tuple[str | None, dict[str, object] | None]:
    if not isinstance(value, str) or not value.strip():
        return None, _error("mcp.invalid_input", "a figure needs executable source")
    if len(value) > _MAX_SOURCE:
        return None, _error("mcp.invalid_input", "a figure needs executable source")
    forbidden = _TIKZ_FORBIDDEN if kind == "tikz" else _PY_FORBIDDEN
    lowered = value.lower()
    if any(token in value or token in lowered for token in forbidden):
        return None, _error("figure.source_forbidden", "figure source must not fetch a URL or leave the book")
    return value, None


def _excerpts(value: object) -> tuple[list[str] | None, dict[str, object] | None]:
    if not isinstance(value, list) or not value:
        return None, _error("mcp.invalid_input", "a figure needs the excerpt ids it illustrates")
    if len(value) > _MAX_EXCERPTS:
        return None, _error("mcp.invalid_input", "too many excerpts to store")
    identifiers: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item.strip()) > 128:
            return None, _error("mcp.invalid_input", "a figure needs the excerpt ids it illustrates")
        cleaned = item.strip()
        if cleaned in identifiers:
            return None, _error("mcp.invalid_input", "excerpts lists the same id more than once")
        identifiers.append(cleaned)
    return identifiers, None


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
        "message": "a figure excerpt cannot support a draft",
        "checked": False,
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
    digest = hashlib.sha256(str(record.get("source_sha256", record.get("source", ""))).encode("utf-8")).hexdigest()
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
    return {"status": code, "message": message, "checked": False}
