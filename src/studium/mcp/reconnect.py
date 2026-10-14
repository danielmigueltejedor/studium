"""Discover whether the running MCP server matches the installed code.

An MCP server is spawned once and keeps serving the code it imported. When the
package on disk changes, a client that holds the old connection silently calls
old tools. This module makes that state visible: it fingerprints the installed
package and lists the tool names the catalog source declares, so a tool call can
say "the running server is stale, reload or restart" instead of leaving the
agent to guess.

``studium_server_reload`` reloads the catalog and the server module in place and
lets the serve loop emit ``notifications/tools/list_changed``. A client that
honours the notification re-lists the tools and sees the new ones. A client that
does not must reconnect; the CLI prints the exact step.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import studium

_TOOL_NAME = re.compile(r'"name"\s*:\s*"(studium_[a-z0-9_]+)"')


def package_root() -> Path:
    return Path(studium.__file__).resolve().parent


def code_fingerprint() -> str:
    """A content hash of every installed ``studium`` module.

    Content, not mtime, so a rewrite that changes nothing does not read as
    stale. ``__pycache__`` is skipped.
    """

    root = package_root()
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def tool_names_on_disk() -> list[str]:
    """The tool names the installed catalog source declares, in file order."""

    catalog = package_root() / "mcp" / "catalog.py"
    source = catalog.read_text(encoding="utf-8")
    seen: list[str] = []
    for name in _TOOL_NAME.findall(source):
        if name not in seen:
            seen.append(name)
    return seen


def reconnect_steps(workspace: str | None = None) -> str:
    target = f" --workspace {workspace}" if workspace else ""
    return (
        "The running server keeps the code it imported. Reload it with "
        "studium_server_reload. If your client does not re-list tools after "
        "notifications/tools/list_changed, restart it: stop the process running "
        f"`studium mcp{target}` and let the client spawn it again, then call "
        "studium_server_info to confirm loaded_code_fingerprint matches "
        "installed_code_fingerprint."
    )


def server_status(
    *,
    loaded_tools: list[str],
    loaded_fingerprint: str,
    workspace: str | None = None,
) -> dict[str, object]:
    installed_tools = tool_names_on_disk()
    installed_fingerprint = code_fingerprint()
    loaded = set(loaded_tools)
    installed = set(installed_tools)
    new_tools = [name for name in installed_tools if name not in loaded]
    removed_tools = [name for name in loaded_tools if name not in installed]
    code_changed = loaded_fingerprint != installed_fingerprint
    stale = bool(new_tools or removed_tools or code_changed)
    payload: dict[str, object] = {
        "status": "ok",
        "loaded_tools": list(loaded_tools),
        "installed_tools": installed_tools,
        "tool_count": len(loaded_tools),
        "loaded_code_fingerprint": loaded_fingerprint,
        "installed_code_fingerprint": installed_fingerprint,
        "code_changed": code_changed,
        "new_tools": new_tools,
        "removed_tools": removed_tools,
        "stale": stale,
        "reloadable": True,
    }
    if stale:
        payload["reconnect"] = reconnect_steps(workspace)
    return payload
