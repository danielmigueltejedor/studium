"""Append-only project records. Callers hold the project lock."""

import json
import os
from pathlib import Path

from studium.domain.ids import IdAllocator

COURSE_CANDIDATES = "course/candidates.jsonl"
PUBLIC_BIBLIOGRAPHY = "bibliography/public.jsonl"
EXCERPTS = "bibliography/excerpts.jsonl"
BLUEPRINT = "blueprint/outline.jsonl"
CLAIMS = "claims/claims.jsonl"
PARAGRAPHS = "draft/paragraphs.jsonl"
SECTION_OFFERS = "draft/section_offers.jsonl"
SECTION_BLOCKS = "draft/section_blocks.jsonl"
PROBLEMS = "problems/problems.jsonl"
COMPUTATIONS = "problems/computations.jsonl"
FIGURES = "figures/figures.jsonl"
AUDITS = "draft/audits.jsonl"
CONTRADICTIONS = "draft/contradictions.jsonl"
REVIEWS = "draft/reviews.jsonl"
MEDIA = "media/media.jsonl"


class RecordCorruption(ValueError):
    """A JSONL file has a damaged record that is not a trailing partial write."""

    def __init__(self, path: Path, lines: list[int]) -> None:
        self.path = path
        self.lines = lines
        super().__init__(f"corrupt records in {path.name}: {lines}")


def atomic_write_text(path: Path, text: str) -> None:
    """Replace a text file only after the new bytes are flushed."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    data = text.encode("utf-8")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        view = data
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("atomic write made no progress")
            view = view[written:]
        os.fsync(descriptor)
    except Exception:
        os.close(descriptor)
        temporary.unlink(missing_ok=True)
        raise
    os.close(descriptor)
    os.replace(temporary, path)


def read_jsonl(path: Path) -> list[dict[str, object]]:
    """Read records. A truncated final line is dropped. A damaged earlier line fails closed."""

    if not path.is_file():
        return []
    raw = path.read_bytes()
    if not raw:
        return []
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise RecordCorruption(path, [1]) from exc
    lines = text.splitlines()
    trailing_partial = not text.endswith(("\n", "\r"))
    rows: list[dict[str, object]] = []
    corrupt: list[int] = []
    last = len(lines) - 1
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            loaded = json.loads(line)
        except json.JSONDecodeError:
            if trailing_partial and index == last:
                continue
            corrupt.append(index + 1)
            continue
        if not isinstance(loaded, dict):
            corrupt.append(index + 1)
            continue
        rows.append(loaded)
    if corrupt:
        raise RecordCorruption(path, corrupt)
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
    data = (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o644)
    try:
        view = data
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("append made no progress")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def allocate_id(root: Path, prefix: str) -> str:
    path = root / ".studium" / "ids.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise TypeError("id document must be an object")
    counters = document.get("counters")
    allocator = IdAllocator(counters if isinstance(counters, dict) else {})
    identifier, allocator = allocator.allocate(prefix)
    document["counters"] = dict(allocator.counters)
    atomic_write_text(path, json.dumps(document, ensure_ascii=False, indent=2) + "\n")
    return identifier
