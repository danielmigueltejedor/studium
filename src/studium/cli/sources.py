"""``studium sources`` calls the same service as the MCP source tools."""

import argparse
import json
from pathlib import Path

from studium.domain.enums import LOCAL_SOURCE_STATUSES
from studium.research.sources import (
    release_safe_metadata,
    source_add,
    source_audit,
    source_get,
    source_impact,
    source_intake_attachment,
    source_list,
    source_register,
    source_reject,
    source_remove,
    source_status,
)

_OK = frozenset({"ok", "imported", "already_registered", "audited"})


def register(subparsers: argparse._SubParsersAction) -> None:
    sources = subparsers.add_parser("sources", help=argparse.SUPPRESS)
    commands = sources.add_subparsers(dest="sources_command")

    status = commands.add_parser("status")
    _project(status)

    add = commands.add_parser("add")
    add.add_argument("files", nargs="*")
    add.add_argument("--origin")
    add.add_argument("--logical")
    add.add_argument("--supersedes")
    add.add_argument("--supports", action="append", default=[])
    add.add_argument("--provided-by")
    add.add_argument("--handle")
    add.add_argument("--filename")
    add.add_argument("--content")
    _project(add)

    listing = commands.add_parser("list")
    _project(listing)

    show = commands.add_parser("get")
    show.add_argument("source_id")
    _project(show)

    audit = commands.add_parser("audit")
    audit.add_argument("source_id")
    audit.add_argument("--role", action="append", default=[])
    audit.add_argument("--class", dest="source_class")
    audit.add_argument("--origin")
    audit.add_argument("--course-authority")
    audit.add_argument("--scientific-authority")
    audit.add_argument("--kind")
    audit.add_argument("--peer-reviewed", choices=("true", "false"))
    audit.add_argument("--supports", action="append", default=[])
    audit.add_argument("--notes")
    _project(audit)

    register_decision = commands.add_parser("register")
    register_decision.add_argument("--decision", choices=("none", "skipped", "available"))
    register_decision.add_argument("--mark-prompted", action="store_true")
    _project(register_decision)

    remove = commands.add_parser("remove")
    remove.add_argument("source_id")
    _project(remove)

    impact = commands.add_parser("impact")
    impact.add_argument("source_id")
    _project(impact)

    reject = commands.add_parser("reject")
    reject.add_argument("source_id")
    reject.add_argument("--reason", required=True)
    _project(reject)

    manifest = commands.add_parser("manifest")
    _project(manifest)


def run(args: argparse.Namespace, root) -> int:
    command = args.sources_command
    if command == "status":
        return _emit(source_status(root), args.json)
    if command == "add":
        return _emit(_add(args, root), args.json)
    if command == "list":
        return _emit(source_list(root), args.json)
    if command == "get":
        return _emit(source_get(root, args.source_id), args.json)
    if command == "audit":
        peer = None if args.peer_reviewed is None else args.peer_reviewed == "true"
        return _emit(
            source_audit(
                root,
                args.source_id,
                roles=args.role or None,
                source_class=args.source_class,
                origin=args.origin,
                course_authority=args.course_authority,
                scientific_authority=args.scientific_authority,
                probable_kind=args.kind,
                peer_reviewed=peer,
                supports=args.supports or None,
                notes=args.notes,
                actor={"kind": "cli"},
            ),
            args.json,
        )
    if command == "register":
        return _emit(
            source_register(
                root,
                decision=args.decision,
                mark_prompted=args.mark_prompted,
                actor={"kind": "cli"},
            ),
            args.json,
        )
    if command == "remove":
        return _emit(source_remove(root, args.source_id, actor={"kind": "cli"}), args.json)
    if command == "impact":
        return _emit(source_impact(root, args.source_id), args.json)
    if command == "reject":
        return _emit(
            source_reject(root, args.source_id, reason=args.reason, actor={"kind": "cli"}),
            args.json,
        )
    if command == "manifest":
        return _emit({"status": "ok", "sources": release_safe_metadata(root)}, args.json)
    return 3


def _add(args: argparse.Namespace, root) -> dict[str, object]:
    if args.handle:
        if not args.content or not args.filename:
            return {"status": "mcp.invalid_input", "message": "handle intake needs filename and content"}
        content_path = Path(args.content)
        if content_path.name in {".env", "id_rsa", "id_ed25519", "credentials.json"}:
            return {"status": "security.credentials_forbidden", "message": "refusing a credential path"}
        try:
            data = content_path.read_bytes()
        except OSError:
            return {"status": "sources.path_not_found", "message": "content file could not be read"}
        return source_intake_attachment(
            root,
            handle=args.handle,
            filename=args.filename,
            content=data,
            logical_id=args.logical,
            supersedes=args.supersedes,
            supports=args.supports,
            provided_by=args.provided_by,
            actor={"kind": "cli"},
        )
    return source_add(
        root,
        list(args.files),
        origin=args.origin,
        logical_id=args.logical,
        supersedes=args.supersedes,
        supports=args.supports,
        provided_by=args.provided_by,
        actor={"kind": "cli"},
    )


def _project(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--project")


def _emit(payload: dict[str, object], as_json: bool) -> int:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(_text(payload))
    status = str(payload.get("status", ""))
    if status in _OK or status in LOCAL_SOURCE_STATUSES:
        return 0
    if status == "project.not_found":
        return 3
    return 1


def _text(payload: dict[str, object]) -> str:
    status = str(payload.get("status", ""))
    if status in LOCAL_SOURCE_STATUSES:
        return (
            f"local_sources.status: {payload.get('status')}\n"
            f"local_sources.prompted: {str(payload.get('prompted')).lower()}\n"
            f"local_sources.source_count: {payload.get('source_count')}\n"
            f"should_ask: {str(payload.get('should_ask')).lower()}"
        )
    sources = payload.get("sources")
    if status == "imported" and isinstance(sources, list):
        lines = [f"{item.get('id')} {item.get('filename')} imported" for item in sources]
        return "\n".join(lines)
    if status == "already_registered":
        return f"already_registered {payload.get('source_id')}"
    if status == "ok" and isinstance(sources, list):
        lines = []
        for item in sources:
            if isinstance(item, dict):
                lines.append(f"{item.get('id')} {item.get('filename')} {item.get('privacy')} {item.get('classification')}")
        if lines:
            return "\n".join(lines)
    return status
