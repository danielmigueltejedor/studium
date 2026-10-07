"""MCP source tools call the same core as the CLI."""

import base64
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from studium.cli.app import main
from studium.mcp.server import dispatch, handle, read_message, tool_names, write_message
from studium.research.attachments import attachment_to_intake

_COURSE = [
    "--course",
    "Mecánica de Fluidos",
    "--university",
    "Universidad de León",
    "--degree",
    "Grado en Ingeniería Aeroespacial",
]
_FORBIDDEN = {
    "arbitrary_shell",
    "arbitrary_file_read",
    "arbitrary_file_write",
    "arbitrary_write_file",
    "find_all_pdfs_in_home",
    "studium_source_add",
    "studium_research_register_source",
}


def _project(tmp_path, monkeypatch, capsys) -> Path:
    monkeypatch.chdir(tmp_path)
    assert main(["create", "fluidos", *_COURSE]) == 0
    capsys.readouterr()
    return tmp_path / "fluidos"


def _pdf(path: Path, body: bytes) -> None:
    path.write_bytes(b"%PDF-1.4\n" + body)


def test_tool_family_is_closed():
    names = set(tool_names())
    assert "studium_project_status" in names
    assert {
        "studium_source_capabilities",
        "studium_source_status",
        "studium_source_list",
        "studium_source_get",
        "studium_source_intake",
        "studium_source_register",
        "studium_source_audit",
        "studium_source_remove",
        "studium_source_impact",
        "studium_source_reject",
    } <= names
    assert names.isdisjoint(_FORBIDDEN)
    listed = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    advertised = {tool["name"] for tool in listed["result"]["tools"]}
    assert advertised == names
    classes = {tool["annotations"]["class"] for tool in listed["result"]["tools"]}
    assert classes <= {"READ", "WRITE", "COMPUTE", "RELEASE"}


def test_project_status_matches_the_cli(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, monkeypatch, capsys)
    assert main(["status", "--json", "--project", str(root)]) == 0
    cli = json.loads(capsys.readouterr().out)
    mcp = dispatch("studium_project_status", {"project": str(root)})
    assert mcp["state"] == cli["state"] == "COURSE_DISCOVERY"
    assert mcp["edition_cycle"] == cli["edition_cycle"]
    assert mcp["local_sources"] == cli["local_sources"]
    assert mcp["course"]["name"] == cli["course"]["name"]
    assert mcp["guidance"] == cli["guidance"]
    assert mcp["guidance"]["should_ask"] is True

    listed = dispatch("studium_source_capabilities", {"project": str(root)})
    assert listed["local_sources_supported"] is True
    assert listed["private_by_default"] is True
    assert listed["auto_upload"] is False
    assert listed["status"] == "UNKNOWN"
    assert listed["prompted"] is False
    assert "xls" in listed["accepted_formats"]
    assert "pdf" in listed["accepted_formats"]


def test_cli_and_mcp_intake_are_the_same_registry(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, monkeypatch, capsys)
    slides = tmp_path / "slides.pdf"
    exam = tmp_path / "exam.pdf"
    _pdf(slides, b"slides")
    _pdf(exam, b"exam-once")
    added = dispatch(
        "studium_source_intake",
        {"project": str(root), "path": str(slides), "origin": "user_uploaded"},
    )
    assert added["status"] == "imported"
    assert added["sources"][0]["id"] == "SRC-0001"
    assert added["sources"][0]["origin"] == "user_uploaded"
    assert main(["sources", "add", str(exam), "--project", str(root), "--json"]) == 0
    capsys.readouterr()
    listed = dispatch("studium_source_list", {"project": str(root)})
    assert [item["id"] for item in listed["sources"]] == ["SRC-0001", "SRC-0002"]
    assert main(["sources", "list", "--project", str(root), "--json"]) == 0
    cli_list = json.loads(capsys.readouterr().out)
    assert cli_list == listed

    status = dispatch("studium_source_status", {"project": str(root)})
    assert main(["sources", "status", "--project", str(root), "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == status
    assert status["status"] == "IMPORTED"
    assert status["source_count"] == 2
    assert {item["id"] for item in status["sources"]} == {"SRC-0001", "SRC-0002"}

    again = dispatch(
        "studium_source_intake",
        {"project": str(root), "path": str(exam)},
    )
    assert again["status"] == "already_registered"
    assert again["source_id"] == "SRC-0002"

    missing = dispatch("studium_source_intake", {"project": str(root)})
    assert missing["status"] == "mcp.invalid_input"
    assert dispatch("studium_source_list", {"project": str(root)})["sources"].__len__() == 2


def test_attachment_adapter_does_not_open_the_handle(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, monkeypatch, capsys)
    secret = tmp_path / "secret-handle.pdf"
    _pdf(secret, b"DO_NOT_READ_THIS_HANDLE")
    content = b"%PDF-1.4\nauthorized-bytes"
    draft = attachment_to_intake(str(secret), "exam-2025.pdf", content)
    assert draft["origin"] == "user_uploaded"
    assert draft["filename"] == "exam-2025.pdf"
    assert draft["content"] == content
    encoded = base64.b64encode(content).decode("ascii")
    imported = dispatch(
        "studium_source_intake",
        {
            "project": str(root),
            "attachment": {
                "handle": str(secret),
                "filename": "notes/exam-2025.pdf",
                "content_base64": encoded,
            },
        },
    )
    assert imported["status"] == "imported"
    source = imported["sources"][0]
    assert source["id"] == "SRC-0001"
    assert source["filename"] == "exam-2025.pdf"
    assert source["origin"] == "user_uploaded"
    assert source["privacy"] == "PRIVATE"
    assert source["classification"] == "PENDING"
    assert source["sha256"] != hashlib.sha256(secret.read_bytes()).hexdigest()
    blob = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in root.rglob("*") if path.is_file())
    assert "DO_NOT_READ_THIS_HANDLE" not in blob
    assert str(secret) not in blob
    refused = dispatch(
        "studium_source_intake",
        {"project": str(root), "attachment": {"handle": str(secret), "filename": "exam.pdf"}},
    )
    assert refused["status"] == "mcp.invalid_input"
    assert len(dispatch("studium_source_list", {"project": str(root)})["sources"]) == 1


def test_mcp_stdio_announces_versions():
    message = {"jsonrpc": "2.0", "id": 7, "method": "initialize"}
    body = json.dumps(message).encode("utf-8")
    framed = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body
    completed = subprocess.run(
        [sys.executable, "-m", "studium", "mcp"],
        input=framed,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0
    parsed = read_message(_Reader(completed.stdout))
    info = parsed["result"]["serverInfo"]
    assert info["name"] == "studium"
    assert info["mcp_api_version"] == "1"
    assert info["schema_version"] == "1.0.0"
    assert "1.0.0a1" in info["version"]


def test_integrations_are_not_a_second_core():
    root = Path(__file__).resolve().parents[1] / "integrations"
    assert not list(root.rglob("*.py"))
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.md"))
    assert "studium mcp" in text
    assert "SRC-LOCAL" not in text


class _Reader:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self._offset = 0

    def readline(self) -> bytes:
        if self._offset >= len(self._data):
            return b""
        end = self._data.find(b"\n", self._offset)
        if end == -1:
            end = len(self._data) - 1
        line = self._data[self._offset : end + 1]
        self._offset = end + 1
        return line

    def read(self, length: int) -> bytes:
        chunk = self._data[self._offset : self._offset + length]
        self._offset += length
        return chunk


def test_write_message_roundtrip():
    sink = _Buffer()
    write_message(sink, {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})
    loaded = read_message(_Reader(sink.data))
    assert loaded["result"]["ok"] is True


class _Buffer:
    def __init__(self) -> None:
        self.data = b""

    def write(self, data: bytes) -> None:
        self.data += data

    def flush(self) -> None:
        return None
