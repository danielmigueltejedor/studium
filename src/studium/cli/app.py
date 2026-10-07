"""Argument parsing, exit codes, and English CLI text."""

import argparse
import json
import os
import re
import sys
import tomllib
from pathlib import Path

from studium import __version__
from studium.authoring.paragraphs import annotate_next_action
from studium.cli.authoring import register as register_authoring
from studium.cli.authoring import run as run_authoring
from studium.cli.sources import register as register_sources
from studium.cli.sources import run as run_sources
from studium.config.resolve import resolve_project
from studium.domain.enums import ProjectState
from studium.domain.profiles import BOOK_TOPIC, PROFILE_CHOICES, TOPIC_BOOK_STATUS
from studium.mcp.http_server import serve_http
from studium.mcp.server import build_parser as register_mcp
from studium.mcp.server import serve as serve_mcp
from studium.research.sources import agent_pack, project_status
from studium.state.gates import PROJECT_TOML, gate_for
from studium.state.machine import earlier_gates_fail
from studium.storage.init_project import (
    SOURCES_MISSING_WARNING,
    build_create_request,
    create_project,
    load_project_toml,
    load_state,
    load_tasks,
    select_next_task,
)

_PROFILES = PROFILE_CHOICES

_WORKFLOW = """\
Workflow:
  studium create <slug> --course STR --university STR --degree STR
          [--academic-year STR] [--course-code STR] [--semester STR]
          [--language STR] [--profile PROFILE] [--sources PATH]
          [--project-dir PATH]
  studium create <slug> --topic STR
          [--language STR] [--profile PROFILE] [--sources PATH]
          [--project-dir PATH]
  studium status [--json] [--project PATH]
  studium next [--json] [--project PATH]
  studium book-next [--json] [--project PATH]
  studium computation --expression STR --result STR [--json] [--project PATH]
  studium run [--project PATH]
  studium blueprint set --section ID TITLE [--section ID TITLE ...] [--json] [--project PATH]
  studium excerpt add --source ID --url URL --text STR [--json] [--project PATH]
  studium paragraph add --section ID --text STR --excerpt ID [--excerpt ID ...] [--json] [--project PATH]
  studium completeness [--json] [--project PATH]
  studium claim add --text STR [--source ID ...] [--excerpt ID ...] [--json] [--project PATH]
  studium verify (--fast | --full) [--entity ID] [--json] [--project PATH]
  studium render [--json] [--project PATH]
  studium build [--project PATH]
  studium release [--project PATH]
  studium mcp [--workspace PATH] [--project PATH] [--http] [--public] [--port PORT] [--token TOKEN]
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
  studium sources status|add|list|audit
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
    if args.command == "sources":
        return _sources(args)
    if args.command in {
        "blueprint",
        "claim",
        "verify",
        "render",
        "excerpt",
        "paragraph",
        "completeness",
        "problem",
        "book-next",
        "computation",
        "media",
        "student-notes",
    }:
        return _authoring(args)
    if args.command == "mcp":
        return _mcp(args)
    if args.command == "agent-pack":
        return _agent_pack(args)
    parser.print_help(sys.stderr)
    return 3


def _build_parser() -> StudiumParser:
    parser = StudiumParser(prog="studium", add_help=True)
    parser.add_argument("--version", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--advanced", action="store_true", help=argparse.SUPPRESS)
    commands = parser.add_subparsers(dest="command")

    create = commands.add_parser("create", help=argparse.SUPPRESS)
    create.add_argument("slug")
    create.add_argument("--course")
    create.add_argument("--topic")
    create.add_argument("--university")
    create.add_argument("--degree")
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

    pack = commands.add_parser("agent-pack", help=argparse.SUPPRESS)
    pack.add_argument("--task")
    pack.add_argument("--json", action="store_true")
    pack.add_argument("--project")
    register_sources(commands)
    register_authoring(commands)
    register_mcp(commands)
    return parser


def _mcp(args: argparse.Namespace) -> int:
    if args.workspace is not None and not Path(args.workspace).expanduser().is_dir():
        print("workspace not found", file=sys.stderr)
        return 3
    if args.port < 1 or args.port > 65535:
        print("invalid port", file=sys.stderr)
        return 3
    if args.public or args.http:
        return serve_http(
            workspace=args.workspace,
            default_project=args.project,
            port=args.port,
            token=args.token,
            public=bool(args.public),
        )
    return serve_mcp(
        sys.stdin.buffer,
        sys.stdout.buffer,
        workspace=args.workspace,
        default_project=args.project,
    )


def _create(args: argparse.Namespace) -> int:
    parent = Path(args.project_dir) if args.project_dir else Path.cwd()
    if not parent.is_dir():
        print("project directory not found", file=sys.stderr)
        return 3

    if args.topic is not None:
        if any((args.course, args.university, args.degree, args.academic_year, args.course_code, args.semester)):
            print("a topic book does not take a university, degree, or course guide", file=sys.stderr)
            return 3
        request, sources_missing = build_create_request(
            slug=args.slug,
            parent=parent,
            topic=args.topic,
            language=args.language,
            profile=args.profile,
            sources=args.sources,
        )
    else:
        if not isinstance(args.course, str) or not isinstance(args.university, str) or not isinstance(args.degree, str):
            print("course, university, and degree are required", file=sys.stderr)
            return 3
        request, sources_missing = build_create_request(
            slug=args.slug,
            parent=parent,
            course=args.course,
            university=args.university,
            degree=args.degree,
            academic_year=args.academic_year,
            course_code=args.course_code,
            semester=args.semester,
            language=args.language,
            profile=args.profile,
            sources=args.sources,
        )
    result = create_project(request)
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
        print(SOURCES_MISSING_WARNING, file=sys.stderr)
    if request.kind == BOOK_TOPIC:
        print(TOPIC_BOOK_STATUS)
        return 0
    print("Studium project created.")
    print("Next: COURSE_DISCOVERY")
    print("Run: studium agent-pack")
    return 0


def _status(args: argparse.Namespace) -> int:
    root = _require_project(args.project)
    if root is None:
        return 3
    try:
        payload = annotate_next_action(root, project_status(root))
    except (OSError, json.JSONDecodeError, UnicodeError, tomllib.TOMLDecodeError, TypeError, AttributeError):
        print("invalid project", file=sys.stderr)
        return 1
    if args.json:
        print(_json(payload))
        return 0
    course = payload.get("course")
    fields = course if isinstance(course, dict) else {}
    local = payload.get("local_sources")
    fields_local = local if isinstance(local, dict) else {}
    print(f"state: {payload.get('state')}")
    print(f"edition: {payload.get('edition', '')}")
    print(f"edition_cycle: {payload.get('edition_cycle')}")
    print(f"local_sources.status: {fields_local.get('status', '')}")
    print(f"local_sources.prompted: {str(fields_local.get('prompted', False)).lower()}")
    print(f"local_sources.source_count: {fields_local.get('source_count', 0)}")
    print(f"course.name: {fields.get('name', '')}")
    if payload.get("book_kind") == BOOK_TOPIC:
        print(f"course.domain_profile: {fields.get('domain_profile', '')}")
        message = payload.get("message")
        if isinstance(message, str):
            print(message)
        action = payload.get("next_action")
        if isinstance(action, str):
            print(f"next_action: {action}")
        _print_writing_status(payload)
        return 0
    print(f"course.university: {fields.get('university', '')}")
    print(f"course.degree: {fields.get('degree', '')}")
    action = payload.get("next_action")
    if isinstance(action, str):
        print(f"next_action: {action}")
    _print_writing_status(payload)
    return 0


def _print_writing_status(payload: dict[str, object]) -> None:
    writing = payload.get("writing_status")
    if isinstance(writing, str):
        print(writing)


def _agent_pack(args: argparse.Namespace) -> int:
    root = _require_project(args.project)
    if root is None:
        return 3
    try:
        payload = agent_pack(root, task=args.task)
    except (OSError, json.JSONDecodeError, UnicodeError, tomllib.TOMLDecodeError, TypeError, AttributeError):
        print("invalid project", file=sys.stderr)
        return 1
    if args.json:
        print(_json(payload))
        return 0
    print(_agent_pack_text(payload))
    return 0


def _agent_pack_text(payload: dict[str, object]) -> str:
    lines = [
        "kind: local_sources",
        "scope: local_sources_only",
        f"course_discovery: {_yes_no(payload.get('course_discovery'))}",
        f"research: {_yes_no(payload.get('research'))}",
        f"task: {payload.get('task') or 'none'}",
        f"local_sources.status: {payload.get('status')}",
        f"local_sources.prompted: {str(payload.get('prompted')).lower()}",
        f"local_sources.source_count: {payload.get('source_count')}",
        f"should_ask: {_yes_no(payload.get('should_ask'))}",
        f"do_not_ask: {_yes_no(payload.get('do_not_ask'))}",
        f"accept_files: {_yes_no(payload.get('accept_files'))}",
        "scan_home: no",
    ]
    if payload.get("writing_available") is False and isinstance(payload.get("message"), str):
        lines.append(str(payload["message"]))
        lines.append("course_guide: no")
    if isinstance(payload.get("next_action"), str):
        lines.append(f"next_action: {payload['next_action']}")
    if isinstance(payload.get("writing_status"), str):
        lines.append(str(payload["writing_status"]))
    status = payload.get("status")
    if payload.get("should_ask") and isinstance(payload.get("question"), str):
        lines.append(f"question: {payload['question']}")
    elif status in {"NONE", "SKIPPED"} or (status == "UNKNOWN" and payload.get("should_ask") is not True):
        lines.append("do not ask again")
    if status == "AVAILABLE":
        lines.append("accept files")
        lines.append("do not scan the home directory")
    sources = payload.get("sources")
    if status == "IMPORTED" and isinstance(sources, list):
        for item in sources:
            if isinstance(item, dict):
                roles = item.get("roles") or []
                role_text = ",".join(str(role) for role in roles) if isinstance(roles, list) else ""
                lines.append(
                    f"{item.get('id')} roles={role_text} classification={item.get('classification')}"
                )
    return "\n".join(lines)


def _yes_no(value: object) -> str:
    return "yes" if value is True else "no"


def _authoring(args: argparse.Namespace) -> int:
    root = _require_project(args.project)
    if root is None:
        return 3
    try:
        return run_authoring(args, root)
    except (OSError, json.JSONDecodeError, UnicodeError, tomllib.TOMLDecodeError, TypeError, AttributeError):
        print("invalid project", file=sys.stderr)
        return 1


def _sources(args: argparse.Namespace) -> int:
    if not getattr(args, "sources_command", None):
        print("unknown command: sources", file=sys.stderr)
        return 3
    root = _require_project(args.project)
    if root is None:
        return 3
    try:
        return run_sources(args, root)
    except (OSError, json.JSONDecodeError, UnicodeError, tomllib.TOMLDecodeError, TypeError, AttributeError):
        print("invalid project", file=sys.stderr)
        return 1


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
    return resolve_project(explicit)


def _json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    raise SystemExit(main())
