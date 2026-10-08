import argparse
import json
import re

import pytest

from studium.cli.app import _build_parser, main

_COURSE = [
    "--course",
    "Mecánica de Fluidos",
    "--university",
    "Universidad de León",
    "--degree",
    "Grado en Ingeniería Aeroespacial",
]

_NEXT = (
    "state: COURSE_DISCOVERY\n"
    "task: TSK-0001 course_discovery\n"
    "pack: studium agent-pack --task TSK-0001\n"
    "blocked: no\n"
)


def test_next_prints_state_and_first_task(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["create", "fluidos", *_COURSE]) == 0
    capsys.readouterr()

    monkeypatch.chdir(tmp_path / "fluidos")
    rc = main(["next"])
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out == _NEXT
    assert captured.err == ""


def test_next_json_and_missing_project(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["next"]) == 3
    assert capsys.readouterr().err.strip() == "project.not_found"

    assert main(["create", "fluidos", *_COURSE]) == 0
    capsys.readouterr()
    rc = main(["next", "--json", "--project", str(tmp_path / "fluidos")])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] == "COURSE_DISCOVERY"
    assert payload["task"] == "TSK-0001"
    assert payload["type"] == "course_discovery"
    assert payload["blocked"] is False


def test_blocked_human_exits_2(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["create", "fluidos", *_COURSE]) == 0
    task_path = tmp_path / "fluidos" / "tasks" / "tasks.jsonl"
    task = json.loads(task_path.read_text(encoding="utf-8"))
    task["status"] = "blocked_human"
    task["blocked_reason"] = "human_decision"
    task_path.write_text(json.dumps(task) + "\n", encoding="utf-8")
    capsys.readouterr()

    rc = main(["next", "--project", str(tmp_path / "fluidos")])
    captured = capsys.readouterr()
    assert rc == 2
    assert "state: COURSE_DISCOVERY" in captured.out
    assert "task: TSK-0001 course_discovery" in captured.out
    assert "blocked: yes" in captured.out


def test_help_advertises_only_registered_commands(capsys, monkeypatch):
    registered: set[str] = set()
    for action in _build_parser()._actions:
        if isinstance(action, argparse._SubParsersAction):
            registered = set(action.choices)
    assert main(["--help"]) == 0
    default = capsys.readouterr().out
    monkeypatch.setenv("STUDIUM_ADVANCED", "1")
    assert main(["--help"]) == 0
    advanced = capsys.readouterr().out
    advertised: set[str] = set()
    for text in (default, advanced):
        advertised.update(re.findall(r"(?m)^  studium ([a-z][a-z0-9-]*)\b", text))
    assert advertised
    assert advertised <= registered
    for hidden in ("run", "build", "release"):
        assert hidden not in advertised
        assert f"studium {hidden}" not in default
        assert f"studium {hidden}" not in advanced


@pytest.mark.parametrize(
    "command",
    ["run", "research", "build", "release", "doctor", "graph", "source"],
)
def test_commands_outside_stage_0_are_unknown(capsys, command):
    rc = main([command, "--task", "TSK-0001"])
    captured = capsys.readouterr()
    assert rc == 3
    assert f"unknown command: {command}" in captured.err
