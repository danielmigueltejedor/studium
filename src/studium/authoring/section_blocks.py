"""Remember a draft section that cannot take another open excerpt or a replayed check.

Blocking a section does not release the book and does not fill the gap.
"""

from pathlib import Path

from studium.storage.locking import ProjectLocked, project_lock
from studium.storage.migrate import utc_now
from studium.storage.records import SECTION_BLOCKS, SECTION_OFFERS, append_jsonl, fold_by_id


def blocked_sections(root: Path) -> list[dict[str, object]]:
    """Sections marked blocked. Empty ones still render as gaps."""

    visible: list[dict[str, object]] = []
    for record in fold_by_id(root / SECTION_BLOCKS):
        if record.get("status") != "blocked":
            continue
        identifier = record.get("section")
        if not isinstance(identifier, str):
            continue
        visible.append(
            {
                "id": identifier,
                "title": record.get("title") if isinstance(record.get("title"), str) else "",
                "reason": record.get("reason") if isinstance(record.get("reason"), str) else "blocked",
            }
        )
    return visible


def blocked_ids(root: Path) -> set[str]:
    return {str(item["id"]) for item in blocked_sections(root)}


def offers_for(root: Path, section_id: str, kind: str) -> list[dict[str, object]]:
    return [
        record
        for record in fold_by_id(root / SECTION_OFFERS)
        if record.get("section") == section_id and record.get("kind") == kind
    ]


def remember_offer(root: Path, *, section_id: str, kind: str, excerpt_id: str | None = None) -> None:
    """Record that book_next already asked for this step. Does not change project state."""

    identifier = f"{kind}:{section_id}" if excerpt_id is None else f"{kind}:{section_id}:{excerpt_id}"
    record: dict[str, object] = {
        "schema_version": "1.0.0",
        "id": identifier,
        "section": section_id,
        "kind": kind,
        "recorded_at": utc_now(),
    }
    if excerpt_id is not None:
        record["excerpt"] = excerpt_id
    try:
        with project_lock(root):
            append_jsonl(root / SECTION_OFFERS, record)
    except ProjectLocked:
        return


def mark_blocked(root: Path, *, section_id: str, title: str, reason: str) -> dict[str, object]:
    """Mark one section blocked. The paragraph gap stays empty."""

    record: dict[str, object] = {
        "schema_version": "1.0.0",
        "id": section_id,
        "section": section_id,
        "title": title,
        "status": "blocked",
        "reason": reason,
        "recorded_at": utc_now(),
    }
    try:
        with project_lock(root):
            append_jsonl(root / SECTION_BLOCKS, record)
    except ProjectLocked:
        return record
    return record
