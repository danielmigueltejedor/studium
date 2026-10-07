"""Argument parsing, exit codes, and English CLI text."""

import argparse
import json
import os
import re
import sys
import tomllib
from pathlib import Path

from studium import __version__
from studium.domain.enums import ProjectState
from studium.state.gates import PROJECT_TOML, gate_for
from studium.state.machine import earlier_gates_fail
from studium.storage.init_project import (
    CreateRequest,
    create_project,
    load_project_toml,
    load_state,
    load_tasks,
    local_sources_label,
    select_next_task,
)

_PROFILES = ("STEM", "HUMANITIES", "SOCIAL_SCIENCES", "COMPUTER_SCIENCE", "LAW")
_SOURCES_WARNING = "sources path not found; continuing with COURSE_DISCOVERY"

_WORKFLOW = """\
Workflow:
  studium create <slug> --course STR --university STR --degree STR
          [--academic-year STR] [--course-code STR] [--semester STR]
          [--language STR] [--profile PROFILE] [--sources PATH]
          [--project-dir PATH]
  studium status [--json] [--project PATH]
  studium next [--json] [--project PATH]
  studium run [--project PATH]
  studium research [--check] [--json] [--project PATH]
  studium verify (--fast | --full) [--entity ID] [--json] [--project PATH]
  studium build [--project PATH]
  studium release [--project PATH]
"""

_ADVANCED = """\
Advanced:
  studium doctor [--project PATH]
  studium graph [--entity ID | --impact ID] [--json]
  studium tasks [--json]
  studium agent-pack [--task TSK-] [--project PATH]
  studium diff <edition-a> <edition-b> [--json]
  studium refresh-course [--project PATH]
"""

_RECORDS = """\
Records:
  studium source ...
  studium claim ...
  studium exercise ...
  studium derivation ...
  studium equation ...
  studium figure ...
  studium review ...
"""


class StudiumParser(argparse.ArgumentParser):
    advanced: bool = False

    def format_usage(self) -> str:
        return "usage: studium [-h] [--version] [--advanced] <command> [<args>]\n"

    def format_help(self) -> str:
        parts = [
            self.format_usage(),
            "\n",
            _WORKFLOW,
            "\n",
            _ADVANCED,
        ]
        if self.advanced:
            parts.extend(["\n", _RECORDS])
        return "".join(parts)

    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        choice = re.search(r"invalid choice:\s+'([^']+)'", message)
        if choice is None:
            choice = re.search(r"invalid choice:\s+(\S+)", message)
        if choice is not None:
            self.exit(3, f"unknown command: {choice.group(1)}\n")
        self.exit(3, f"error: {message}\n")


def main(argv: list[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    parser = _build_parser()
    parser.advanced = os.environ.get("STUDIUM_ADVANCED") == "1" or "--advanced" in args_list
    try:
        args = parser.parse_args(args_list)
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        return int(code) if isinstance(code, int) else 1

    if args.version:
        print(f"studium {__version__}")
        return 0
    if args.command == "create":
        return _create(args)
    if args.command == "status":
        return _status(args)
    if args.command == "next":
        return _next(args)
    parser.print_help(sys.stderr)
    return 3


def _build_parser() -> StudiumParser:
    parser = StudiumParser(prog="studium", add_help=True)
    parser.add_argument("--version", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--advanced", action="store_true", help=argparse.SUPPRESS)
    commands = parser.add_subparsers(dest="command")

    create = commands.add_parser("create", help=argparse.SUPPRESS)
    create.add_argument("slug")
    create.add_argument("--course", required=True)
    create.add_argument("--university", required=True)
    create.add_argument("--degree", required=True)
    create.add_argument("--academic-year")
    create.add_argument("--course-code")
    create.add_argument("--semester")
    create.add_argument("--language")
    create.add_argument("--profile", choices=_PROFILES)
    create.add_argument("--sources")
    create.add_argument("--project-dir")

    status = commands.add_parser("status", help=argparse.SUPPRESS)
    status.add_argument("--json", action="store_true")
    status.add_argument("--project")

    nxt = commands.add_parser("next", help=argparse.SUPPRESS)
    nxt.add_argument("--json", action="store_true")
    nxt.add_argument("--project")
    return parser


def _create(args: argparse.Namespace) -> int:
    parent = Path(args.project_dir) if args.project_dir else Path.cwd()
    if not parent.is_dir():
        print("project directory not found", file=sys.stderr)
        return 3

    sources_missing = False
    label = None
    if args.sources:
        label = local_sources_label(args.sources)
        if not Path(args.sources).exists():
            sources_missing = True

    result = create_project(
        CreateRequest(
            slug=args.slug,
            parent=parent,
            name=args.course,
            university=args.university,
            degree=args.degree,
            academic_year=args.academic_year,
            course_code=args.course_code,
            semester=args.semester,
            language=args.language,
            domain_profile=args.profile or "GENERAL",
            local_sources=label,
            local_sources_missing=sources_missing,
        )
    )
    if result.failure == "invalid_slug":
        print("invalid slug", file=sys.stderr)
        return 3
    if result.failure == "invalid_profile":
        print("invalid profile", file=sys.stderr)
        return 3
    if result.failure == "already_exists":
        print("project already exists", file=sys.stderr)
        return 1
    if result.failure == "gate":
        for blocker in result.blockers:
            print(f"{blocker.code}: {blocker.message}", file=sys.stderr)
        return 1
    if result.root is None:
        print("project.not_found", file=sys.stderr)
        return 3

    if sources_missing:
        print(_SOURCES_WARNING, file=sys.stderr)
    print("Studium project created.")
    print("Next: COURSE_DISCOVERY")
    print("Run: studium agent-pack")
    return 0


def _status(args: argparse.Namespace) -> int:
    root = _require_project(args.project)
    if root is None:
        return 3
    try:
        state = load_state(root)
        document = load_project_toml(root)
    except (OSError, json.JSONDecodeError, UnicodeError, tomllib.TOMLDecodeError, TypeError, AttributeError):
        print("invalid project", file=sys.stderr)
        return 1
    if args.json:
        course = document.get("course")
        payload = {
            "schema_version": state.get("schema_version"),
            "state": state.get("state"),
            "edition": document.get("edition"),
            "edition_cycle": state.get("edition_cycle"),
            "local_sources_missing": state.get("local_sources_missing"),
            "history": state.get("history"),
            "course": course if isinstance(course, dict) else {},
        }
        print(_json(payload))
        return 0
    course = document.get("course")
    fields = course if isinstance(course, dict) else {}
    print(f"state: {state.get('state')}")
    print(f"edition: {document.get('edition', '')}")
    print(f"edition_cycle: {state.get('edition_cycle')}")
    print(f"local_sources_missing: {str(state.get('local_sources_missing')).lower()}")
    print(f"course.name: {fields.get('name', '')}")
    print(f"course.university: {fields.get('university', '')}")
    print(f"course.degree: {fields.get('degree', '')}")
    return 0


def _next(args: argparse.Namespace) -> int:
    root = _require_project(args.project)
    if root is None:
        return 3
    try:
        state_document = load_state(root)
        project = load_project_toml(root)
        tasks = load_tasks(root)
        project_state = ProjectState(str(state_document["state"]))
    except (
        OSError,
        json.JSONDecodeError,
        UnicodeError,
        tomllib.TOMLDecodeError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
    ):
        print("invalid project", file=sys.stderr)
        return 1

    course = project.get("course")
    gates = {PROJECT_TOML: gate_for(PROJECT_TOML, course if isinstance(course, dict) else {})}
    if earlier_gates_fail(project_state, gates):
        payload = {
            "state": project_state.value,
            "action": "regress",
            "task": None,
            "type": None,
            "pack": None,
            "blocked": False,
        }
        if args.json:
            print(_json(payload))
        else:
            print(f"state: {project_state.value}")
            print("action: regress")
            print("blocked: no")
        return 0

    task = select_next_task(tasks, project_state.value)
    blocked = task is not None and task.get("status") == "blocked_human"
    task_id = None if task is None else str(task["id"])
    task_type = None if task is None else str(task["type"])
    pack = None if task_id is None else f"studium agent-pack --task {task_id}"
    if args.json:
        print(
            _json(
                {
                    "state": project_state.value,
                    "action": "task",
                    "task": task_id,
                    "type": task_type,
                    "pack": pack,
                    "blocked": blocked,
                }
            )
        )
    elif task is None:
        print(f"state: {project_state.value}")
        print("task: none")
        print("pack: none")
        print("blocked: no")
    else:
        print(f"state: {project_state.value}")
        print(f"task: {task_id} {task_type}")
        print(f"pack: {pack}")
        print(f"blocked: {'yes' if blocked else 'no'}")
    return 2 if blocked else 0


def _require_project(explicit: str | None) -> Path | None:
    root = _resolve_project(explicit)
    if root is None:
        print("project.not_found", file=sys.stderr)
        return None
    return root


def _resolve_project(explicit: str | None) -> Path | None:
    if explicit is not None:
        candidate = Path(explicit).expanduser().resolve()
        return candidate if _is_project(candidate) else None
    env = os.environ.get("STUDIUM_PROJECT")
    if env:
        candidate = Path(env).expanduser().resolve()
        return candidate if _is_project(candidate) else None
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if _is_project(candidate):
            return candidate
    return None


def _is_project(path: Path) -> bool:
    return (path / "project.toml").is_file() and (path / ".studium" / "state.json").is_file()


def _json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    raise SystemExit(main())
