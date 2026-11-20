"""Create an independent, improvable edition without overwriting the previous book."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from pathlib import Path

from studium.agents.adaptive import workflow_start
from studium.config.resolve import is_project
from studium.storage.init_project import load_project_toml
from studium.storage.locking import ProjectLocked, project_lock
from studium.storage.migrate import utc_now
from studium.storage.records import (
    AUDITS,
    CONTRADICTIONS,
    REVIEWS,
    SECTION_OFFERS,
    atomic_write_text,
)

_METADATA = ".studium/edition.json"
_SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_EDITION_PATTERN = re.compile(r'^edition = "([^"\n]+)"$', re.MULTILINE)


def _version(root: Path) -> str:
    document = load_project_toml(root)
    edition = document.get("edition")
    return str(edition) if isinstance(edition, str) else "0.1.0"


def _index(root: Path) -> int:
    metadata = root / _METADATA
    if metadata.is_file():
        value = json.loads(metadata.read_text(encoding="utf-8")).get("index")
        if isinstance(value, int) and value >= 2:
            return value
    return 1


def _family(root: Path) -> str:
    metadata = root / _METADATA
    if metadata.is_file():
        value = json.loads(metadata.read_text(encoding="utf-8")).get("family")
        if isinstance(value, str) and value:
            return value
    return root.name


def _has_symlinks(root: Path) -> bool:
    for folder, directories, files in os.walk(root, followlinks=False):
        if any((Path(folder) / name).is_symlink() for name in [*directories, *files]):
            return True
    return False


def list_editions(root: Path) -> dict[str, object]:
    family = _family(root)
    versions: list[dict[str, object]] = []
    for candidate in root.parent.iterdir():
        if not candidate.is_dir() or candidate.is_symlink() or not is_project(candidate):
            continue
        if _family(candidate) != family:
            continue
        versions.append({
            "project": candidate.name,
            "index": _index(candidate),
            "version": _version(candidate),
            "current": candidate == root,
        })
    versions.sort(key=lambda item: (int(item["index"]), str(item["project"])))
    return {"status": "ok", "family": family, "editions": versions}


def create_edition(
    root: Path, *, request: object, version: object = None, discipline: object = None
) -> dict[str, object]:
    """Fork a complete project into a new sibling edition, resetting edition-level review.

    No model is invoked and no quality gate is bypassed. The original project
    and its previous PDF remain untouched. The client carries out the new plan.
    """
    if not isinstance(request, str) or not request.strip() or len(request) > 4000:
        return {"status": "mcp.invalid_input", "message": "Describe the desired improvements (1-4000 chars)."}
    if version is not None and (not isinstance(version, str) or _SEMVER.fullmatch(version) is None):
        return {"status": "mcp.invalid_input", "message": "version must be MAJOR.MINOR.PATCH"}
    if _has_symlinks(root):
        return {"status": "edition.unsafe_source", "message": "Cannot fork a project containing symlinks."}

    family = _family(root)
    siblings = list_editions(root)["editions"]
    index = max(int(item["index"]) for item in siblings) + 1
    destination = root.parent / f"{family}-edition-{index}"
    if destination.exists():
        return {"status": "edition.exists", "message": "Destination already exists."}

    current_version = _version(root)
    current = _SEMVER.fullmatch(current_version)
    if current is None:
        return {"status": "edition.invalid_version", "message": "Current edition is not semantic MAJOR.MINOR.PATCH"}
    if version is None:
        # Advance from the highest existing version, not only the source book.
        parsed = [_SEMVER.fullmatch(str(item["version"])) for item in siblings]
        highest = max((tuple(map(int, match.groups())) for match in parsed if match is not None),
                      default=tuple(map(int, current.groups())))
        new_version = f"{highest[0]}.{highest[1] + 1}.0"
    else:
        new_version = version
        if tuple(map(int, _SEMVER.fullmatch(new_version).groups())) <= tuple(map(int, current.groups())):
            return {"status": "edition.invalid_version", "message": "New version must exceed source version."}

    # The new draft is not released or academically reviewed just because its
    # content came from a previously reviewed manuscript.
    tempdir: Path | None = None
    try:
        with project_lock(root):
            tempdir = Path(tempfile.mkdtemp(prefix=".studium-edition-", dir=root.parent))
            draft = tempdir / destination.name
            shutil.copytree(
                root,
                draft,
                symlinks=True,
                ignore=shutil.ignore_patterns("write.lock", "__pycache__", ".pytest_cache", ".git", ".venv", "venv"),
            )
            project_toml = draft / "project.toml"
            text = project_toml.read_text(encoding="utf-8")
            replacement, count = _EDITION_PATTERN.subn(f'edition = "{new_version}"', text, count=1)
            if count != 1:
                return {"status": "edition.invalid_project", "message": "project.toml has no edition key"}
            atomic_write_text(project_toml, replacement)

            state_path = draft / ".studium" / "state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["edition_cycle"] = int(state.get("edition_cycle", 1)) + 1
            if state.get("state") == "RELEASED":
                state["state"] = "SOURCE_DISCOVERY"
            atomic_write_text(state_path, json.dumps(state, ensure_ascii=False, indent=2) + "\n")

            for relative in (AUDITS, CONTRADICTIONS, REVIEWS, SECTION_OFFERS):
                (draft / relative).unlink(missing_ok=True)
            (draft / ".studium" / "agent-workflow.json").unlink(missing_ok=True)
            # No stale generated PDF may be advertised as the new edition.
            latex = draft / "latex"
            if latex.is_dir():
                for item in latex.glob("draft.*"):
                    if item.is_file() and not item.is_symlink():
                        item.unlink()
            metadata = {
                "schema_version": "1.0.0",
                "family": family,
                "index": index,
                "version": new_version,
                "source_project": root.name,
                "source_version": current_version,
                "request": request.strip(),
                "created_at": utc_now(),
                "publication": "draft",
                "academic_review": "not_established",
            }
            atomic_write_text(draft / _METADATA, json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
            draft.rename(destination)
    except ProjectLocked:
        return {"status": "storage.locked", "message": "project is locked"}
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return {"status": "edition.failed", "message": str(exc)}
    finally:
        if tempdir is not None:
            shutil.rmtree(tempdir, ignore_errors=True)

    # Delegation is ready for external Claude/ChatGPT/Codex clients. It is not
    # autonomous, and a partial plan is not a successfully generated book.
    started = workflow_start(destination, objective="edition", discipline=discipline)
    return {
        "status": "created",
        "project": destination.name,
        "path": str(destination),
        "version": new_version,
        "parent": root.name,
        "request": request.strip(),
        "original_untouched": True,
        "review_required": True,
        "workflow": started,
        "next_tool": "studium_agent_workflow_next",
        "note": "Agents must improve the copied draft and rerun Studium verification, review and rendering.",
    }
