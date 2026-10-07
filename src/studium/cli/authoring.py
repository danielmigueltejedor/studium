"""CLI for the draft path. Same functions as the MCP tools."""

import argparse
import json
import sys
from pathlib import Path

from studium.authoring.blueprint import get_blueprint, store_blueprint
from studium.authoring.claims import list_claims, record_claim
from studium.authoring.render import render_draft
from studium.authoring.verify import verify_book

EXIT_GATE = 2
EXIT_COMPILER = 4
_OK = frozenset({"ok", "recorded", "rendered"})


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
    add.add_argument("--source", action="append", required=True)
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
                    sources=list(args.source),
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
    blockers = payload.get("blockers")
    if isinstance(blockers, list) and blockers:
        return "\n".join(
            f"{item.get('code')}: {item.get('message')}" for item in blockers if isinstance(item, dict)
        )
    message = payload.get("message")
    return str(message) if isinstance(message, str) else status


def _yes_no(value: object) -> str:
    return "yes" if value is True else "no"
