"""Local MCP stdio server for the source tool family and project status."""

import argparse
import base64
import json
from collections.abc import Mapping
from pathlib import Path
from typing import BinaryIO

from studium import __version__
from studium.config.resolve import resolve_project
from studium.mcp import MCP_API_VERSION
from studium.research.sources import (
    project_status,
    source_add,
    source_audit,
    source_capabilities,
    source_get,
    source_impact,
    source_intake_attachment,
    source_list,
    source_register,
    source_reject,
    source_remove,
    source_status,
)

SCHEMA_VERSION = "1.0.0"

_TOOLS: tuple[dict[str, object], ...] = (
    {"name": "studium_project_status", "class": "READ"},
    {"name": "studium_source_capabilities", "class": "READ"},
    {"name": "studium_source_status", "class": "READ"},
    {"name": "studium_source_list", "class": "READ"},
    {"name": "studium_source_get", "class": "READ"},
    {"name": "studium_source_impact", "class": "READ"},
    {"name": "studium_source_intake", "class": "WRITE"},
    {"name": "studium_source_register", "class": "WRITE"},
    {"name": "studium_source_audit", "class": "WRITE"},
    {"name": "studium_source_remove", "class": "WRITE"},
    {"name": "studium_source_reject", "class": "WRITE"},
)

_FORBIDDEN = frozenset(
    {
        "arbitrary_shell",
        "arbitrary_file_read",
        "arbitrary_file_write",
        "arbitrary_write_file",
        "find_all_pdfs_in_home",
    }
)


def tool_names() -> list[str]:
    return [str(tool["name"]) for tool in _TOOLS]


def handle(message: Mapping[str, object], *, default_project: str | None = None) -> dict[str, object] | None:
    method = message.get("method")
    if method == "notifications/initialized":
        return None
    request_id = message.get("id")
    if method == "initialize":
        return _result(
            request_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "studium",
                    "version": __version__,
                    "mcp_api_version": MCP_API_VERSION,
                    "schema_version": SCHEMA_VERSION,
                },
            },
        )
    if method == "tools/list":
        return _result(request_id, {"tools": [_schema(tool) for tool in _TOOLS]})
    if method == "tools/call":
        params = message.get("params")
        if not isinstance(params, dict):
            return _result(request_id, _tool_body({"status": "mcp.invalid_input", "message": "params required"}, True))
        name = params.get("name")
        arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        if not isinstance(name, str) or name not in tool_names():
            return _result(
                request_id,
                _tool_body({"status": "mcp.unknown_tool", "message": "tool is not in the closed set"}, True),
            )
        if name in _FORBIDDEN:
            return _result(request_id, _tool_body({"status": "security.credentials_forbidden", "message": "refused"}, True))
        payload = dispatch(name, arguments, default_project=default_project)
        return _result(request_id, _tool_body(payload, _failed(payload)))
    return _result(request_id, _tool_body({"status": "mcp.unknown_method", "message": "method is not supported"}, True))


def dispatch(name: str, arguments: Mapping[str, object], *, default_project: str | None = None) -> dict[str, object]:
    root = _root(arguments, default_project)
    if root is None:
        return {"status": "project.not_found", "message": "project.not_found"}
    actor = arguments.get("actor") if isinstance(arguments.get("actor"), dict) else {"kind": "mcp"}
    if name == "studium_project_status":
        return project_status(root)
    if name == "studium_source_capabilities":
        return source_capabilities(root)
    if name == "studium_source_status":
        return source_status(root)
    if name == "studium_source_list":
        return source_list(root)
    if name == "studium_source_get":
        source_id = arguments.get("source_id")
        if not isinstance(source_id, str):
            return {"status": "mcp.invalid_input", "message": "source_id is required"}
        return source_get(root, source_id)
    if name == "studium_source_impact":
        source_id = arguments.get("source_id")
        if not isinstance(source_id, str):
            return {"status": "mcp.invalid_input", "message": "source_id is required"}
        return source_impact(root, source_id)
    if name == "studium_source_intake":
        return _intake(root, arguments, actor)
    if name == "studium_source_register":
        decision = arguments.get("decision")
        mark = arguments.get("mark_prompted") is True
        if decision is not None and not isinstance(decision, str):
            return {"status": "mcp.invalid_input", "message": "decision must be a string"}
        return source_register(root, decision=decision, mark_prompted=mark, actor=actor)
    if name == "studium_source_audit":
        return _audit(root, arguments, actor)
    if name == "studium_source_remove":
        source_id = arguments.get("source_id")
        if not isinstance(source_id, str):
            return {"status": "mcp.invalid_input", "message": "source_id is required"}
        return source_remove(root, source_id, actor=actor)
    if name == "studium_source_reject":
        source_id = arguments.get("source_id")
        reason = arguments.get("reason")
        if not isinstance(source_id, str) or not isinstance(reason, str):
            return {"status": "mcp.invalid_input", "message": "source_id and reason are required"}
        return source_reject(root, source_id, reason=reason, actor=actor)
    return {"status": "mcp.unknown_tool", "message": "tool is not in the closed set"}


def serve(stdin: BinaryIO, stdout: BinaryIO, *, default_project: str | None = None) -> int:
    while True:
        message = read_message(stdin)
        if message is None:
            return 0
        response = handle(message, default_project=default_project)
        if response is not None:
            write_message(stdout, response)


def read_message(stream: BinaryIO) -> dict[str, object] | None:
    first = stream.readline()
    if not first:
        return None
    lowered = first.lower()
    if lowered.startswith(b"content-length:"):
        length = int(first.split(b":", 1)[1].strip())
        while True:
            line = stream.readline()
            if line in (b"\r\n", b"\n", b""):
                break
        body = stream.read(length)
        loaded = json.loads(body.decode("utf-8"))
        if not isinstance(loaded, dict):
            raise TypeError("mcp message must be an object")
        return loaded
    loaded = json.loads(first.decode("utf-8"))
    if not isinstance(loaded, dict):
        raise TypeError("mcp message must be an object")
    return loaded


def write_message(stream: BinaryIO, message: Mapping[str, object]) -> None:
    body = json.dumps(message, ensure_ascii=False).encode("utf-8")
    stream.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body)
    stream.flush()


def build_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("mcp", help=argparse.SUPPRESS)
    parser.add_argument("--project")


def _intake(root: Path, arguments: Mapping[str, object], actor: dict[str, object]) -> dict[str, object]:
    logical = arguments.get("logical_id") if isinstance(arguments.get("logical_id"), str) else None
    supersedes = arguments.get("supersedes") if isinstance(arguments.get("supersedes"), str) else None
    supports = _str_list(arguments.get("supports"))
    origin = arguments.get("origin") if isinstance(arguments.get("origin"), str) else None
    attachment = arguments.get("attachment")
    if attachment is not None:
        if not isinstance(attachment, dict):
            return {"status": "mcp.invalid_input", "message": "attachment must be an object"}
        encoded = attachment.get("content_base64")
        handle = attachment.get("handle")
        filename = attachment.get("filename")
        if not isinstance(encoded, str) or not isinstance(handle, str) or not isinstance(filename, str):
            return {"status": "mcp.invalid_input", "message": "attachment needs handle, filename, and content"}
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError):
            return {"status": "mcp.invalid_input", "message": "attachment content is not base64"}
        return source_intake_attachment(
            root,
            handle=handle,
            filename=filename,
            content=content,
            logical_id=logical,
            supersedes=supersedes,
            supports=supports,
            actor=actor,
        )
    paths: list[str] = []
    if isinstance(arguments.get("path"), str):
        paths.append(str(arguments["path"]))
    extra = arguments.get("paths")
    if isinstance(extra, list):
        if not all(isinstance(item, str) for item in extra):
            return {"status": "mcp.invalid_input", "message": "paths must be strings"}
        paths.extend(extra)
    if not paths:
        return {"status": "mcp.invalid_input", "message": "path or attachment is required"}
    return source_add(
        root,
        paths,
        origin=origin,
        logical_id=logical,
        supersedes=supersedes,
        supports=supports,
        actor=actor,
    )


def _audit(root: Path, arguments: Mapping[str, object], actor: dict[str, object]) -> dict[str, object]:
    source_id = arguments.get("source_id")
    if not isinstance(source_id, str):
        return {"status": "mcp.invalid_input", "message": "source_id is required"}
    peer = arguments.get("peer_reviewed")
    if peer is not None and not isinstance(peer, bool):
        return {"status": "mcp.invalid_input", "message": "peer_reviewed must be a boolean"}
    return source_audit(
        root,
        source_id,
        roles=_optional_str_list(arguments.get("roles")),
        source_class=arguments.get("source_class") if isinstance(arguments.get("source_class"), str) else None,
        origin=arguments.get("origin") if isinstance(arguments.get("origin"), str) else None,
        course_authority=arguments.get("course_authority") if isinstance(arguments.get("course_authority"), str) else None,
        scientific_authority=(
            arguments.get("scientific_authority") if isinstance(arguments.get("scientific_authority"), str) else None
        ),
        probable_kind=arguments.get("probable_kind") if isinstance(arguments.get("probable_kind"), str) else None,
        peer_reviewed=peer if isinstance(peer, bool) else None,
        supports=_optional_str_list(arguments.get("supports")),
        notes=arguments.get("notes") if isinstance(arguments.get("notes"), str) else None,
        actor=actor,
    )


def _root(arguments: Mapping[str, object], default_project: str | None) -> Path | None:
    explicit = arguments.get("project")
    if explicit is not None and not isinstance(explicit, str):
        return None
    chosen = explicit if isinstance(explicit, str) else default_project
    return resolve_project(chosen)


def _schema(tool: Mapping[str, object]) -> dict[str, object]:
    return {
        "name": tool["name"],
        "description": f"{tool['class']} tool {tool['name']}",
        "inputSchema": {
            "type": "object",
            "properties": {"project": {"type": "string"}},
            "additionalProperties": True,
        },
        "annotations": {"class": tool["class"]},
    }


def _tool_body(payload: Mapping[str, object], is_error: bool) -> dict[str, object]:
    text = json.dumps(payload, ensure_ascii=False)
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": dict(payload),
        "isError": is_error,
    }


def _result(request_id: object, result: Mapping[str, object]) -> dict[str, object]:
    return {"jsonrpc": "2.0", "id": request_id, "result": dict(result)}


def _failed(payload: Mapping[str, object]) -> bool:
    status = str(payload.get("status", "ok"))
    if status in {"ok", "imported", "already_registered", "audited"}:
        return False
    if status in {"UNKNOWN", "NONE", "AVAILABLE", "IMPORTED", "SKIPPED"}:
        return False
    if "state" in payload and "local_sources" in payload:
        return False
    if payload.get("local_sources_supported") is True:
        return False
    return True


def _str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _optional_str_list(value: object) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None
    return list(value)
