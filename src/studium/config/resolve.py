"""Find the project root. The same rules for the CLI and for MCP."""

import os
from pathlib import Path


def resolve_project(explicit: str | None = None) -> Path | None:
    if explicit is not None:
        candidate = Path(explicit).expanduser().resolve()
        return candidate if is_project(candidate) else None
    env = os.environ.get("STUDIUM_PROJECT")
    if env:
        candidate = Path(env).expanduser().resolve()
        return candidate if is_project(candidate) else None
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if is_project(candidate):
            return candidate
    return None


def is_project(path: Path) -> bool:
    return (path / "project.toml").is_file() and (path / ".studium" / "state.json").is_file()
