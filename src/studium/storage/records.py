"""Append-only project records. Callers hold the project lock."""

import json
from pathlib import Path

from studium.domain.ids import IdAllocator

COURSE_CANDIDATES = "course/candidates.jsonl"
PUBLIC_BIBLIOGRAPHY = "bibliography/public.jsonl"
EXCERPTS = "bibliography/excerpts.jsonl"
BLUEPRINT = "blueprint/outline.jsonl"
CLAIMS = "claims/claims.jsonl"


def read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.is_file():
        return []
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        loaded = json.loads(line)
        if isinstance(loaded, dict):
            rows.append(loaded)
    return rows


def fold_by_id(path: Path) -> list[dict[str, object]]:
    folded: dict[str, dict[str, object]] = {}
    order: list[str] = []
    for record in read_jsonl(path):
        if "id" not in record:
            continue
        identifier = str(record["id"])
        if identifier not in folded:
            order.append(identifier)
        folded[identifier] = record
    visible: list[dict[str, object]] = []
    for identifier in order:
        record = folded[identifier]
        if record.get("deleted") is True:
            continue
        visible.append(record)
    return visible


def append_jsonl(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def allocate_id(root: Path, prefix: str) -> str:
    path = root / ".studium" / "ids.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise TypeError("id document must be an object")
    counters = document.get("counters")
    allocator = IdAllocator(counters if isinstance(counters, dict) else {})
    identifier, allocator = allocator.allocate(prefix)
    document["counters"] = dict(allocator.counters)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return identifier
