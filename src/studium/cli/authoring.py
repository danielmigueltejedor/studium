"""CLI for the draft path. Same functions as the MCP tools."""

import argparse
import json
import sys
from pathlib import Path

from studium.authoring.blueprint import get_blueprint, store_blueprint
from studium.authoring.book_next import book_next
from studium.authoring.claims import list_claims, record_claim
from studium.authoring.computation import check_computation
from studium.authoring.excerpts import get_excerpt, list_excerpts, record_excerpt
from studium.authoring.paragraphs import draft_completeness, list_paragraphs, record_paragraph
from studium.authoring.problems import check_problem, list_problems, record_problem
from studium.authoring.render import render_draft
from studium.authoring.verify import verify_book

EXIT_GATE = 2
EXIT_COMPILER = 4
_OK = frozenset({"ok", "recorded", "rendered", "replayed"})


def register(subparsers: argparse._SubParsersAction) -> None:
    blueprint = subparsers.add_parser("blueprint", help=argparse.SUPPRESS)
    blueprint_commands = blueprint.add_subparsers(dest="blueprint_command")
    store = blueprint_commands.add_parser("set")
    store.add_argument("--section", action="append", nargs=2, metavar=("ID", "TITLE"), required=True)
    _project(store)
    show = blueprint_commands.add_parser("get")
    _project(show)

    claim = subparsers.add_parser("claim", help=argparse.SUPPRESS)
    claim_commands = claim.add_subparsers(dest="claim_command")
    add = claim_commands.add_parser("add")
    add.add_argument("--text", required=True)
    add.add_argument("--source", action="append")
    add.add_argument("--excerpt", action="append")
    add.add_argument("--section")
    _project(add)
    listing = claim_commands.add_parser("list")
    _project(listing)

    verify = subparsers.add_parser("verify", help=argparse.SUPPRESS)
    mode = verify.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fast", action="store_true")
    mode.add_argument("--full", action="store_true")
    verify.add_argument("--entity")
    _project(verify)

    render = subparsers.add_parser("render", help=argparse.SUPPRESS)
    _project(render)

    excerpt = subparsers.add_parser("excerpt", help=argparse.SUPPRESS)
    excerpt_commands = excerpt.add_subparsers(dest="excerpt_command")
    store = excerpt_commands.add_parser("add")
    store.add_argument("--source", required=True)
    store.add_argument("--url", required=True)
    store.add_argument("--text", required=True)
    _project(store)
    excerpt_list = excerpt_commands.add_parser("list")
    _project(excerpt_list)
    excerpt_get = excerpt_commands.add_parser("get")
    excerpt_get.add_argument("excerpt_id")
    _project(excerpt_get)

    paragraph = subparsers.add_parser("paragraph", help=argparse.SUPPRESS)
    paragraph_commands = paragraph.add_subparsers(dest="paragraph_command")
    paragraph_add = paragraph_commands.add_parser("add")
    paragraph_add.add_argument("--section", required=True)
    paragraph_add.add_argument("--text", required=True)
    paragraph_add.add_argument("--excerpt", action="append", required=True)
    _project(paragraph_add)
    paragraph_list = paragraph_commands.add_parser("list")
    _project(paragraph_list)

    completeness = subparsers.add_parser("completeness", help=argparse.SUPPRESS)
    _project(completeness)

    problem = subparsers.add_parser("problem", help=argparse.SUPPRESS)
    problem_commands = problem.add_subparsers(dest="problem_command")
    problem_add = problem_commands.add_parser("add")
    problem_add.add_argument("--section", required=True)
    problem_add.add_argument("--prompt", required=True)
    problem_add.add_argument("--source-text")
    problem_add.add_argument("--invocation", nargs="+")
    problem_add.add_argument("--expected")
    problem_add.add_argument("--excerpt", action="append")
    _project(problem_add)
    problem_check = problem_commands.add_parser("check")
    problem_check.add_argument("problem_id")
    _project(problem_check)
    problem_list = problem_commands.add_parser("list")
    _project(problem_list)

    book = subparsers.add_parser("book-next", help=argparse.SUPPRESS)
    _project(book)

    computation = subparsers.add_parser("computation", help=argparse.SUPPRESS)
    computation.add_argument("--expression")
    computation.add_argument("--result")
    computation.add_argument("--id")
    computation.add_argument("--section")
    _project(computation)


def run(args: argparse.Namespace, root: Path) -> int:
    command = args.command
    if command == "blueprint":
        if args.blueprint_command == "set":
            sections = [{"id": section_id, "title": title} for section_id, title in args.section]
            return _emit(store_blueprint(root, sections, actor={"kind": "cli"}), args.json)
        if args.blueprint_command == "get":
            return _emit(get_blueprint(root), args.json)
        print("unknown command: blueprint", file=sys.stderr)
        return 3
    if command == "claim":
        if args.claim_command == "add":
            return _emit(
                record_claim(
                    root,
                    text=args.text,
                    sources=list(args.source) if args.source else None,
                    excerpts=list(args.excerpt) if args.excerpt else None,
                    section=args.section,
                    actor={"kind": "cli"},
                ),
                args.json,
            )
        if args.claim_command == "list":
            return _emit(list_claims(root), args.json)
        print("unknown command: claim", file=sys.stderr)
        return 3
    if command == "verify":
        mode_name = "fast" if args.fast else "full"
        return _emit(verify_book(root, mode=mode_name, entity=args.entity), args.json)
    if command == "render":
        return _emit(render_draft(root), args.json)
    if command == "excerpt":
        if args.excerpt_command == "add":
            return _emit(
                record_excerpt(
                    root,
                    source_id=args.source,
                    url=args.url,
                    text=args.text,
                    actor={"kind": "cli"},
                ),
                args.json,
            )
        if args.excerpt_command == "list":
            return _emit(list_excerpts(root), args.json)
        if args.excerpt_command == "get":
            return _emit(get_excerpt(root, args.excerpt_id), args.json)
        print("unknown command: excerpt", file=sys.stderr)
        return 3
    if command == "paragraph":
        if args.paragraph_command == "add":
            return _emit(
                record_paragraph(
                    root,
                    section=args.section,
                    text=args.text,
                    excerpts=list(args.excerpt),
                    actor={"kind": "cli"},
                ),
                args.json,
            )
        if args.paragraph_command == "list":
            return _emit(list_paragraphs(root), args.json)
        print("unknown command: paragraph", file=sys.stderr)
        return 3
    if command == "completeness":
        return _emit(draft_completeness(root), args.json)
    if command == "problem":
        if args.problem_command == "add":
            return _emit(
                record_problem(
                    root,
                    section=args.section,
                    prompt=args.prompt,
                    source_text=args.source_text,
                    invocation=list(args.invocation) if args.invocation else None,
                    expected=args.expected,
                    excerpts=list(args.excerpt) if args.excerpt else None,
                    actor={"kind": "cli"},
                ),
                args.json,
            )
        if args.problem_command == "check":
            return _emit(check_problem(root, args.problem_id), args.json)
        if args.problem_command == "list":
            return _emit(list_problems(root), args.json)
        print("unknown command: problem", file=sys.stderr)
        return 3
    if command == "book-next":
        return _emit(book_next(root), args.json)
    if command == "computation":
        return _emit(
            check_computation(
                root,
                expression=args.expression,
                result=args.result,
                computation_id=args.id,
                section=args.section,
                actor={"kind": "cli"},
            ),
            args.json,
        )
    print("unknown command", file=sys.stderr)
    return 3


def _project(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--project")


def _emit(payload: dict[str, object], as_json: bool) -> int:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(_text(payload))
        message = payload.get("message")
        if payload.get("status") not in _OK and isinstance(message, str):
            print(message, file=sys.stderr)
    return _code(payload)


def _code(payload: dict[str, object]) -> int:
    status = str(payload.get("status", ""))
    if status in _OK:
        return 0
    if status == "gate":
        return EXIT_GATE
    if status == "compiler_missing":
        return EXIT_COMPILER
    if status == "project.not_found":
        return 3
    return 1


def _text(payload: dict[str, object]) -> str:
    status = str(payload.get("status", ""))
    if "reason" in payload and "ask_user" in payload:
        tool = payload.get("tool")
        return "\n".join(
            [
                f"tool: {tool if isinstance(tool, str) else 'none'}",
                f"reason: {payload.get('reason')}",
                "ask_user: no",
                f"released: {_yes_no(payload.get('released'))}",
            ]
        )
    if status == "gate":
        lines = [
            f"state: {payload.get('project_state')}",
            f"released: {_yes_no(payload.get('released'))}",
            "applied: no",
            "blockers:",
        ]
        blockers = payload.get("blockers")
        if isinstance(blockers, list):
            for blocker in blockers:
                if isinstance(blocker, dict):
                    lines.append(f"  {blocker.get('code')}: {blocker.get('message')}")
        drafts = payload.get("draft_claims")
        if isinstance(drafts, list):
            lines.append("draft_claims: " + (", ".join(str(item) for item in drafts) if drafts else "none"))
        return "\n".join(lines)
    if status in {"rendered", "compiler_missing", "render.compile_failed"}:
        pdf = payload.get("pdf")
        lines = [
            f"state: {payload.get('project_state')}",
            f"released: {_yes_no(payload.get('released'))}",
            f"tex: {payload.get('tex')}",
            f"pdf: {pdf if isinstance(pdf, str) else 'none'}",
        ]
        return "\n".join(lines)
    if "blueprint" in payload and status in {"ok", "recorded"}:
        blueprint = payload.get("blueprint")
        if not isinstance(blueprint, dict):
            return "blueprint: none"
        sections = blueprint.get("sections")
        lines = [f"blueprint: {blueprint.get('id')}"]
        if isinstance(sections, list):
            for section in sections:
                if isinstance(section, dict):
                    lines.append(f"{section.get('id')}: {section.get('title')}")
        return "\n".join(lines)
    claims = payload.get("claims")
    if status == "ok" and isinstance(claims, list):
        if not claims:
            return "claims: none"
        lines = []
        for claim in claims:
            if isinstance(claim, dict):
                lines.append(f"{claim.get('id')} {claim.get('status')}")
        return "\n".join(lines)
    claim = payload.get("claim")
    if status == "recorded" and isinstance(claim, dict):
        return f"{claim.get('id')} status: draft"
    excerpt = payload.get("excerpt")
    if status in {"recorded", "already_recorded", "ok"} and isinstance(excerpt, dict):
        return f"{excerpt.get('id')} source: {excerpt.get('source_id')} classification: PENDING"
    paragraphs = payload.get("paragraphs")
    if status == "ok" and isinstance(paragraphs, list):
        if not paragraphs:
            return "paragraphs: none"
        return "\n".join(
            f"{item.get('id')} {item.get('section')} {item.get('status')}"
            for item in paragraphs
            if isinstance(item, dict)
        )
    paragraph = payload.get("paragraph")
    if status in {"recorded", "already_recorded"} and isinstance(paragraph, dict):
        return f"{paragraph.get('id')} status: draft"
    if status == "ok" and "supported_section_count" in payload:
        empty = payload.get("empty_sections")
        names = "none"
        if isinstance(empty, list) and empty:
            names = ", ".join(
                f"{item.get('id')} ({item.get('title')})" for item in empty if isinstance(item, dict)
            )
        return (
            f"supported_sections: {payload.get('supported_section_count')}"
            f"/{payload.get('section_count')}\nempty: {names}"
        )
    excerpts = payload.get("excerpts")
    if status == "ok" and isinstance(excerpts, list):
        if not excerpts:
            return "excerpts: none"
        return "\n".join(
            f"{item.get('id')} source: {item.get('source_id')}" for item in excerpts if isinstance(item, dict)
        )
    blockers = payload.get("blockers")
    if isinstance(blockers, list) and blockers:
        return "\n".join(
            f"{item.get('code')}: {item.get('message')}" for item in blockers if isinstance(item, dict)
        )
    message = payload.get("message")
    return str(message) if isinstance(message, str) else status


def _yes_no(value: object) -> str:
    return "yes" if value is True else "no"
