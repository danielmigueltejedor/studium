import json
import subprocess
import sys
import tomllib

import pytest

from studium import __version__
from studium.cli.app import main

_COURSE = [
    "--course",
    "Mecánica de Fluidos",
    "--university",
    "Universidad de León",
    "--degree",
    "Grado en Ingeniería Aeroespacial",
]

_CREATED = (
    "Studium project created.\n"
    "Next: COURSE_DISCOVERY\n"
    "Run: studium agent-pack\n"
)


def test_create_writes_the_four_files_and_the_stdout_contract(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    rc = main(["create", "fluidos", *_COURSE])
    captured = capsys.readouterr()

    assert rc == 0
    assert captured.out == _CREATED
    assert captured.err == ""

    root = tmp_path / "fluidos"
    files = sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())
    assert files == [
        ".studium/ids.json",
        ".studium/state.json",
        "project.toml",
        "tasks/tasks.jsonl",
    ]

    text = (root / "project.toml").read_text(encoding="utf-8")
    assert "Mecánica de Fluidos" in text
    assert "Universidad de León" in text
    assert "Grado en Ingeniería Aeroespacial" in text
    document = tomllib.loads(text)
    assert document["schema_version"] == "1.0.0"
    assert document["edition"] == "0.1.0"
    assert document["course"]["name"] == "Mecánica de Fluidos"
    assert document["course"]["university"] == "Universidad de León"
    assert document["course"]["degree"] == "Grado en Ingeniería Aeroespacial"
    assert document["course"]["domain_profile"] == "GENERAL"

    state = json.loads((root / ".studium" / "state.json").read_text(encoding="utf-8"))
    assert state["schema_version"] == "1.0.0"
    assert state["state"] == "COURSE_DISCOVERY"
    assert state["edition_cycle"] == 1
    assert "local_sources_missing" not in state
    assert state["local_sources"]["status"] == "UNKNOWN"
    assert state["local_sources"]["prompted"] is False
    assert state["local_sources"]["source_count"] == 0
    assert state["local_sources"]["last_updated"]
    assert state["history"] == [
        {"from": None, "to": "CREATED", "event": "project_created"},
        {"from": "CREATED", "to": "COURSE_DISCOVERY", "event": "begin_discovery"},
    ]

    identifiers = json.loads((root / ".studium" / "ids.json").read_text(encoding="utf-8"))
    assert identifiers["schema_version"] == "1.0.0"
    assert identifiers["counters"] == {"TSK": 1}

    task = json.loads((root / "tasks" / "tasks.jsonl").read_text(encoding="utf-8"))
    assert task["schema_version"] == "1.0.0"
    assert task["id"] == "TSK-0001"
    assert task["type"] == "course_discovery"
    assert task["project_state"] == "COURSE_DISCOVERY"
    assert task["status"] == "open"
    assert task["dependencies"] == []


def test_missing_sources_exit_zero_and_stay_unknown(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    missing = tmp_path / "private-notes"
    rc = main(["create", "fluidos", *_COURSE, "--sources", str(missing)])
    captured = capsys.readouterr()

    assert rc == 0
    assert captured.out == _CREATED
    assert captured.err == "sources path not found; continuing with COURSE_DISCOVERY\n"

    root = tmp_path / "fluidos"
    state = json.loads((root / ".studium" / "state.json").read_text(encoding="utf-8"))
    assert "local_sources_missing" not in state
    assert state["state"] == "COURSE_DISCOVERY"
    assert state["local_sources"]["status"] == "UNKNOWN"
    assert state["local_sources"]["prompted"] is False
    assert state["local_sources"]["source_count"] == 0
    text = (root / "project.toml").read_text(encoding="utf-8")
    assert str(missing) not in text
    assert 'local_sources = "private-notes"' in text
    assert not (root / "sources").exists()


def test_existing_sources_are_not_copied(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    sources = tmp_path / "private-notes"
    sources.mkdir()
    (sources / "secret.pdf").write_bytes(b"%PDF-1.4 secret")

    rc = main(["create", "fluidos", *_COURSE, "--sources", str(sources)])
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out == _CREATED
    assert captured.err == ""

    root = tmp_path / "fluidos"
    state = json.loads((root / ".studium" / "state.json").read_text(encoding="utf-8"))
    assert "local_sources_missing" not in state
    assert state["local_sources"]["status"] == "AVAILABLE"
    assert state["local_sources"]["prompted"] is False
    assert state["local_sources"]["source_count"] == 0
    assert list(root.rglob("secret.pdf")) == []
    files = sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())
    assert files == [
        ".studium/ids.json",
        ".studium/state.json",
        "project.toml",
        "tasks/tasks.jsonl",
    ]


@pytest.mark.parametrize("slug", ["Fluidos", "bad_slug", "bad--slug", "bad-"])
def test_illegal_slug_exits_3(tmp_path, monkeypatch, capsys, slug):
    monkeypatch.chdir(tmp_path)
    rc = main(["create", slug, *_COURSE])
    captured = capsys.readouterr()
    assert rc == 3
    assert captured.out == ""
    assert "invalid slug" in captured.err
    assert not (tmp_path / slug).exists()


def test_slug_that_looks_like_a_flag_exits_3(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    rc = main(["create", "-bad", *_COURSE])
    captured = capsys.readouterr()
    assert rc == 3
    assert captured.out == ""
    assert not (tmp_path / "-bad").exists()


def test_create_does_not_overwrite_an_existing_project(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["create", "fluidos", *_COURSE]) == 0
    capsys.readouterr()
    rc = main(["create", "fluidos", "--course", "Other", "--university", "Other", "--degree", "Other"])
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert "project already exists" in captured.err
    document = tomllib.loads((tmp_path / "fluidos" / "project.toml").read_text(encoding="utf-8"))
    assert document["course"]["name"] == "Mecánica de Fluidos"


def test_blank_course_name_does_not_create_a_project(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    rc = main(["create", "fluidos", "--course", " ", "--university", "U", "--degree", "D"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "state.project_fields_missing" in captured.err
    assert not (tmp_path / "fluidos").exists()


def test_optional_course_fields_and_profile(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    rc = main(
        [
            "create",
            "mecanica-de-fluidos",
            *_COURSE,
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
        ]
    )
    assert rc == 0
    document = tomllib.loads((tmp_path / "mecanica-de-fluidos" / "project.toml").read_text(encoding="utf-8"))
    course = document["course"]
    assert course["academic_year"] == "2025-2026"
    assert course["course_code"] == "AE-101"
    assert course["semester"] == "2"
    assert course["language"] == "es"
    assert course["domain_profile"] == "STEM"


def test_version_and_help_panels(capsys, monkeypatch):
    assert __version__ == "1.0.0a1"
    assert main(["--version"]) == 0
    assert capsys.readouterr().out == "studium 1.0.0a1\n"

    completed = subprocess.run(
        [sys.executable, "-m", "studium", "--version"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert completed.stdout == "studium 1.0.0a1\n"

    assert main(["--help"]) == 0
    help_text = capsys.readouterr().out
    assert "studium create <slug>" in help_text
    assert "studium status [--json] [--project PATH]" in help_text
    assert "studium next [--json] [--project PATH]" in help_text
    assert "studium agent-pack [--task TSK-] [--project PATH]" in help_text
    assert "studium source" not in help_text

    monkeypatch.setenv("STUDIUM_ADVANCED", "1")
    assert main(["--help"]) == 0
    advanced = capsys.readouterr().out
    assert "studium sources status|add|list|get|audit|register|remove|impact|reject" in advanced
    assert "studium source ..." not in advanced
    assert "studium review" in advanced


def test_status_reads_the_project_from_flag_env_and_parents(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["create", "fluidos", *_COURSE]) == 0
    capsys.readouterr()

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    rc = main(["status", "--project", str(tmp_path / "fluidos")])
    assert rc == 0
    assert "state: COURSE_DISCOVERY" in capsys.readouterr().out

    monkeypatch.setenv("STUDIUM_PROJECT", str(tmp_path / "fluidos"))
    rc = main(["status", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] == "COURSE_DISCOVERY"
    assert payload["course"]["name"] == "Mecánica de Fluidos"

    nested = tmp_path / "fluidos" / "notes"
    nested.mkdir()
    monkeypatch.chdir(nested)
    monkeypatch.delenv("STUDIUM_PROJECT")
    rc = main(["status"])
    assert rc == 0
    assert "course.university: Universidad de León" in capsys.readouterr().out

    monkeypatch.setenv("STUDIUM_PROJECT", str(tmp_path / "missing"))
    rc = main(["status"])
    captured = capsys.readouterr()
    assert rc == 3
    assert captured.err.strip() == "project.not_found"
    assert captured.out == ""
