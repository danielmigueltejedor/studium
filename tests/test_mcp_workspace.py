"""MCP binds to a workspace and can create a book without a pre-existing project."""

import json
import os
import subprocess
import sys
from io import BytesIO
from pathlib import Path

from studium.cli.app import main
from studium.mcp.server import dispatch, handle, open_workspace, read_message, serve, write_message
from studium.storage.init_project import SOURCES_MISSING_WARNING

_COURSE = {
    "course": "Mecánica de Fluidos",
    "university": "Universidad de León",
    "degree": "Grado en Ingeniería Aeroespacial",
}
_CLI_COURSE = [
    "--course",
    _COURSE["course"],
    "--university",
    _COURSE["university"],
    "--degree",
    _COURSE["degree"],
]


def test_server_starts_with_no_project_and_status_says_create(tmp_path):
    incoming = BytesIO()
    _write(incoming, {"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    _write(
        incoming,
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "studium_project_status", "arguments": {}}},
    )
    _write(incoming, {"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
    incoming.seek(0)
    outgoing = BytesIO()
    assert serve(incoming, outgoing, workspace=str(tmp_path)) == 0
    outgoing.seek(0)
    initialized = read_message(outgoing)
    status = read_message(outgoing)
    listed = read_message(outgoing)
    assert initialized["result"]["protocolVersion"] == "2024-11-05"
    payload = status["result"]["structuredContent"]
    assert status["result"]["isError"] is False
    assert payload["next_action"] == "create"
    assert payload["tool"] == "studium_project_create"
    assert payload["active_project"] is None
    names = {tool["name"] for tool in listed["result"]["tools"]}
    assert "studium_project_create" in names
    assert "studium_project_list" in names
    assert not (tmp_path / "project.toml").exists()


def test_cli_mcp_starts_without_a_project(tmp_path):
    message = {"jsonrpc": "2.0", "id": 1, "method": "initialize"}
    body = json.dumps(message).encode("utf-8")
    framed = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body
    completed = subprocess.run(
        [sys.executable, "-m", "studium", "mcp"],
        cwd=tmp_path,
        input=framed,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0
    parsed = read_message(BytesIO(completed.stdout))
    assert parsed["result"]["serverInfo"]["name"] == "studium"
    assert b"project.not_found" not in completed.stderr


def test_create_then_status_uses_the_new_book(tmp_path):
    session = open_workspace(str(tmp_path))
    assert session is not None
    created = dispatch("studium_project_create", {"slug": "fluidos", **_COURSE}, session=session)
    assert created["status"] == "created"
    assert Path(created["path"]) == (tmp_path / "fluidos").resolve()
    status = dispatch("studium_project_status", {}, session=session)
    assert status["state"] == "COURSE_DISCOVERY"
    assert status["course"]["name"] == _COURSE["course"]
    listed = dispatch("studium_project_list", {}, session=session)
    assert [item["slug"] for item in listed["projects"]] == ["fluidos"]

    incoming = BytesIO()
    _write(
        incoming,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "studium_project_create",
                "arguments": {"slug": "termo", **_COURSE},
            },
        },
    )
    _write(
        incoming,
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "studium_project_status", "arguments": {}}},
    )
    incoming.seek(0)
    outgoing = BytesIO()
    assert serve(incoming, outgoing, workspace=str(tmp_path)) == 0
    outgoing.seek(0)
    first = read_message(outgoing)["result"]["structuredContent"]
    second = read_message(outgoing)["result"]["structuredContent"]
    assert first["status"] == "created"
    assert second["state"] == "COURSE_DISCOVERY"
    assert second["course"]["university"] == _COURSE["university"]
    assert (tmp_path / "termo" / "project.toml").is_file()


def test_path_escape_is_rejected(tmp_path):
    workspace = tmp_path / "books"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_session = open_workspace(str(outside))
    assert dispatch("studium_project_create", {"slug": "secret", **_COURSE}, session=outside_session)["status"] == "created"
    link = workspace / "linked"
    link.symlink_to(outside / "secret", target_is_directory=True)

    session = open_workspace(str(workspace))
    for raw in ("../outside/secret", str(outside / "secret"), "linked", "fluidos/../../outside/secret"):
        escaped = dispatch("studium_project_status", {"project": raw}, session=session)
        assert escaped["status"] == "project.escape", raw
    assert dispatch("studium_project_create", {"slug": "../evil", **_COURSE}, session=session)["status"] == "invalid_slug"
    assert not (tmp_path / "evil").exists()
    listed = dispatch("studium_project_list", {}, session=session)
    assert listed["projects"] == []
    assert "secret" not in json.dumps(listed)


def test_duplicate_slug_does_not_replace_the_book(tmp_path):
    session = open_workspace(str(tmp_path))
    created = dispatch("studium_project_create", {"slug": "fluidos", **_COURSE}, session=session)
    assert created["status"] == "created"
    snapshot = _files(tmp_path / "fluidos")
    duplicate = dispatch("studium_project_create", {"slug": "fluidos", **_COURSE}, session=session)
    assert duplicate["status"] == "already_exists"
    assert _files(tmp_path / "fluidos") == snapshot
    status = dispatch("studium_project_status", {}, session=session)
    assert status["course"]["name"] == _COURSE["course"]


def test_create_does_not_scan_home_or_shell_out(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    (home / "notes.pdf").write_bytes(b"%PDF-1.4 secret-home")
    decoy_parent = home / "decoy"
    decoy_parent.mkdir()
    decoy = open_workspace(str(decoy_parent))
    assert dispatch(
        "studium_project_create",
        {"slug": "hidden", "course": "SECRET_HOME_COURSE", "university": "U", "degree": "D"},
        session=decoy,
    )["status"] == "created"

    def explode(*_args, **_kwargs):
        raise AssertionError("home scan or shell")

    monkeypatch.setattr(Path, "home", explode)
    monkeypatch.setattr(os, "walk", explode)
    monkeypatch.setattr(subprocess, "run", explode)
    monkeypatch.setattr(subprocess, "Popen", explode)

    workspace = tmp_path / "books"
    workspace.mkdir()
    session = open_workspace(str(workspace))
    created = dispatch("studium_project_create", {"slug": "fluidos", **_COURSE}, session=session)
    listed = dispatch("studium_project_list", {}, session=session)
    assert created["status"] == "created"
    assert [item["slug"] for item in listed["projects"]] == ["fluidos"]
    blob = json.dumps(listed)
    assert "SECRET_HOME_COURSE" not in blob
    assert "secret-home" not in blob
    assert not (home / "fluidos").exists()
    source = (Path(__file__).resolve().parents[1] / "src" / "studium" / "mcp" / "server.py").read_text(encoding="utf-8")
    assert "subprocess" not in source
    assert "Path.home(" not in source


def test_cli_and_mcp_create_match(tmp_path, monkeypatch, capsys):
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    missing = tmp_path / "private-notes"
    monkeypatch.chdir(tmp_path)
    assert main(
        [
            "create",
            "fluidos",
            *_CLI_COURSE,
            "--academic-year",
            "2025-2026",
            "--course-code",
            "AE-101",
            "--semester",
            "2",
            "--language",
            "es",
            "--profile",
            "STEM",
            "--sources",
            str(missing),
            "--project-dir",
            str(left),
        ]
    ) == 0
    captured = capsys.readouterr()
    assert SOURCES_MISSING_WARNING in captured.err
    session = open_workspace(str(right))
    created = dispatch(
        "studium_project_create",
        {
            "slug": "fluidos",
            **_COURSE,
            "academic_year": "2025-2026",
            "course_code": "AE-101",
            "semester": "2",
            "language": "es",
            "profile": "STEM",
            "sources": str(missing),
        },
        session=session,
    )
    assert created["status"] == "created"
    assert created["warning"] == SOURCES_MISSING_WARNING
    assert _normalized(left / "fluidos") == _normalized(right / "fluidos")


def test_optional_project_flag_still_selects_an_existing_book(tmp_path):
    books = tmp_path / "books"
    books.mkdir()
    session = open_workspace(str(books))
    assert dispatch("studium_project_create", {"slug": "fluidos", **_COURSE}, session=session)["status"] == "created"
    empty = tmp_path / "empty"
    empty.mkdir()
    incoming = BytesIO()
    _write(
        incoming,
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "studium_project_status", "arguments": {}}},
    )
    incoming.seek(0)
    outgoing = BytesIO()
    assert serve(incoming, outgoing, workspace=str(empty), default_project=str(books / "fluidos")) == 0
    outgoing.seek(0)
    payload = read_message(outgoing)["result"]["structuredContent"]
    assert payload["state"] == "COURSE_DISCOVERY"
    escaped = dispatch("studium_project_status", {"project": str(books / "fluidos")}, session=open_workspace(str(empty)))
    assert escaped["status"] == "project.escape"


def test_absolute_path_inside_the_workspace_still_works(tmp_path):
    session = open_workspace(str(tmp_path))
    dispatch("studium_project_create", {"slug": "fluidos", **_COURSE}, session=session)
    status = dispatch("studium_project_status", {"project": str(tmp_path / "fluidos")}, session=session)
    assert status["state"] == "COURSE_DISCOVERY"
    slug = dispatch("studium_project_status", {"project": "fluidos"}, session=session)
    assert slug["course"]["degree"] == _COURSE["degree"]


def test_chatgpt_readme_points_at_the_public_url_form():
    text = (Path(__file__).resolve().parents[1] / "integrations" / "chatgpt" / "README.md").read_text(encoding="utf-8")
    assert "Nombre" in text
    assert "Studium" in text
    assert "URL del servidor" in text
    assert "studium mcp --public" in text
    assert "sin autenticación" in text
    assert "OAuth" in text
    assert "https://github.com/danielmigueltejedor/studium" not in text
    assert "--project" not in text


def test_handle_unknown_tool_still_closed():
    response = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "find_all_pdfs_in_home"}})
    assert response["result"]["isError"] is True


def _write(stream: BytesIO, message: dict) -> None:
    write_message(stream, message)


def _files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _normalized(root: Path) -> tuple[str, dict, dict]:
    toml_text = (root / "project.toml").read_text(encoding="utf-8")
    state = json.loads((root / ".studium" / "state.json").read_text(encoding="utf-8"))
    state["local_sources"]["last_updated"] = "TIME"
    task = json.loads((root / "tasks" / "tasks.jsonl").read_text(encoding="utf-8"))
    task["created_at"] = "TIME"
    task["updated_at"] = "TIME"
    return toml_text, state, task
