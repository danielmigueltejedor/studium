"""agent-pack reports local-source guidance and does not invent research."""

import json
from pathlib import Path

from studium.cli.app import main
from studium.research.guidance import QUESTION_EN, QUESTION_ES, local_source_guidance
from studium.research.sources import agent_pack, source_status

_COURSE = [
    "--course",
    "Cálculo II",
    "--university",
    "Universidad X",
    "--degree",
    "Titulación Y",
]
_MARKER = b"UNIQUE_PRIVATE_BYTES_9f3a"


def _create(tmp_path, monkeypatch, capsys, *extra):
    monkeypatch.chdir(tmp_path)
    assert main(["create", "curso", *_COURSE, *extra]) == 0
    capsys.readouterr()
    return tmp_path / "curso"


def _pdf(path: Path, body: bytes) -> None:
    path.write_bytes(b"%PDF-1.4\n" + body)


def _run(root, capsys, *args):
    rc = main([*args, "--project", str(root), "--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out) if captured.out else None
    return rc, payload, captured


def _matches_status(pack, status):
    for key in ("status", "prompted", "source_count", "should_ask", "do_not_ask", "question", "sources"):
        assert pack[key] == status[key]
    assert "capabilities" not in pack
    assert "sha256" not in json.dumps(pack)
    assert _MARKER.decode() not in json.dumps(pack)


def test_unknown_asks_once_with_the_plain_question(tmp_path, monkeypatch, capsys):
    root = _create(tmp_path, monkeypatch, capsys)
    rc, pack, captured = _run(root, capsys, "agent-pack", "--task", "TSK-0001")
    assert rc == 0
    assert captured.err == ""
    status = source_status(root)
    _matches_status(pack, status)
    assert pack == agent_pack(root, task="TSK-0001")
    assert pack["kind"] == "local_sources"
    assert pack["scope"] == "local_sources_only"
    assert pack["course_discovery"] is False
    assert pack["research"] is False
    assert pack["task"] == "TSK-0001"
    assert pack["status"] == "UNKNOWN"
    assert pack["should_ask"] is True
    assert pack["question"] == QUESTION_EN
    assert pack["accept_files"] is False
    assert pack["scan_home"] is False
    assert pack["sources"] == []

    rc = main(["agent-pack", "--project", str(root)])
    text = capsys.readouterr().out
    assert rc == 0
    assert f"question: {QUESTION_EN}" in text
    assert "course_discovery: no" in text
    assert "research: no" in text
    assert "scan_home: no" in text

    _run(root, capsys, "sources", "register", "--mark-prompted")
    _rc, quiet, _captured = _run(root, capsys, "agent-pack")
    assert quiet["status"] == "UNKNOWN"
    assert quiet["should_ask"] is False
    assert quiet["do_not_ask"] is True
    assert quiet["question"] is None
    assert quiet["course_discovery"] is False
    rc = main(["agent-pack", "--project", str(root)])
    assert "do not ask again" in capsys.readouterr().out


def test_none_and_skipped_do_not_ask_again(tmp_path, monkeypatch, capsys):
    root = _create(tmp_path, monkeypatch, capsys)
    _run(root, capsys, "sources", "register", "--decision", "none")
    rc, pack, _captured = _run(root, capsys, "agent-pack")
    assert rc == 0
    assert pack["status"] == "NONE"
    assert pack["should_ask"] is False
    assert pack["do_not_ask"] is True
    assert pack["question"] is None
    assert pack["accept_files"] is False
    assert pack["scan_home"] is False
    rc = main(["agent-pack", "--project", str(root)])
    text = capsys.readouterr().out
    assert rc == 0
    assert "do not ask again" in text
    assert "question:" not in text

    other = tmp_path / "other"
    other.mkdir()
    skipped = _create(other, monkeypatch, capsys, "--language", "es")
    _run(skipped, capsys, "sources", "register", "--decision", "skipped")
    rc, pack, _captured = _run(skipped, capsys, "agent-pack", "--task", "TSK-0001")
    assert rc == 0
    assert pack["status"] == "SKIPPED"
    assert pack["question"] is None
    assert pack["course_discovery"] is False
    assert pack["research"] is False
    rc = main(["agent-pack", "--project", str(skipped)])
    assert "do not ask again" in capsys.readouterr().out


def test_available_accepts_files_without_scanning_home(tmp_path, monkeypatch, capsys):
    folder = tmp_path / "notes"
    folder.mkdir()
    root = _create(tmp_path, monkeypatch, capsys, "--sources", str(folder))
    rc, pack, _captured = _run(root, capsys, "agent-pack")
    assert rc == 0
    _matches_status(pack, source_status(root))
    assert pack["status"] == "AVAILABLE"
    assert pack["source_count"] == 0
    assert pack["accept_files"] is True
    assert pack["scan_home"] is False
    assert pack["should_ask"] is False
    assert pack["sources"] == []
    rc = main(["agent-pack", "--project", str(root)])
    text = capsys.readouterr().out
    assert rc == 0
    assert "accept files" in text
    assert "do not scan the home directory" in text
    assert "scan_home: no" in text


def test_imported_reports_ids_roles_and_classification_without_bytes(tmp_path, monkeypatch, capsys):
    root = _create(tmp_path, monkeypatch, capsys)
    pdf = tmp_path / "notes.pdf"
    _pdf(pdf, _MARKER)
    rc, imported, _captured = _run(root, capsys, "sources", "add", str(pdf))
    assert rc == 0
    assert imported["sources"][0]["id"] == "SRC-0001"

    rc, pack, _captured = _run(root, capsys, "agent-pack", "--task", "TSK-0001")
    assert rc == 0
    _matches_status(pack, source_status(root))
    assert pack["status"] == "IMPORTED"
    assert pack["accept_files"] is False
    assert pack["scan_home"] is False
    assert pack["course_discovery"] is False
    assert pack["research"] is False
    assert pack["sources"] == [{"id": "SRC-0001", "roles": [], "classification": "PENDING"}]
    rendered = json.dumps(pack)
    assert "sha256" not in rendered
    assert "filename" not in rendered
    assert _MARKER.decode() not in rendered
    assert str(pdf) not in rendered

    rc = main(["agent-pack", "--project", str(root)])
    text = capsys.readouterr().out
    assert rc == 0
    assert "SRC-0001 roles= classification=PENDING" in text
    assert _MARKER.decode() not in text

    rc, audited, _captured = _run(
        root,
        capsys,
        "sources",
        "audit",
        "SRC-0001",
        "--role",
        "COURSE_TERMINOLOGY",
        "--role",
        "LECTURE_EMPHASIS",
    )
    assert rc == 0
    assert audited["status"] == "audited"
    rc, pack, _captured = _run(root, capsys, "agent-pack")
    assert pack["sources"] == [
        {
            "id": "SRC-0001",
            "roles": ["COURSE_TERMINOLOGY", "LECTURE_EMPHASIS"],
            "classification": "AUDITED",
        }
    ]
    rc = main(["agent-pack", "--project", str(root)])
    text = capsys.readouterr().out
    assert "SRC-0001 roles=COURSE_TERMINOLOGY,LECTURE_EMPHASIS classification=AUDITED" in text
    assert _MARKER.decode() not in text


def test_questions_say_materials_are_optional_and_do_not_promise_research():
    assert "optional" in QUESTION_EN
    assert "just say so" in QUESTION_EN
    assert "opcionales" in QUESTION_ES
    assert "basta con decirlo" in QUESTION_ES
    for question in (QUESTION_EN, QUESTION_ES):
        lowered = question.casefold()
        assert "research" not in lowered
        assert "investig" not in lowered
        assert "course guide" not in lowered
        assert "guía oficial" not in question
        assert "authoritative" not in lowered
    spanish = local_source_guidance({"status": "UNKNOWN", "prompted": False}, [], "es")
    assert spanish["question"] == QUESTION_ES
    english = local_source_guidance({"status": "UNKNOWN", "prompted": False}, [], "en")
    assert english["question"] == QUESTION_EN


def test_missing_project_is_not_an_unknown_command(capsys):
    rc = main(["agent-pack", "--task", "TSK-0001"])
    captured = capsys.readouterr()
    assert rc == 3
    assert captured.err.strip() == "project.not_found"
    assert "unknown command" not in captured.err
