"""Which public sources may support a draft claim.

The model is not a source. A stored year, title, or ISBN conflict cannot
support a claim. On a course book, a source that is not marked as cited by
the stored guide cannot support a claim. A topic book does not require a
university guide.
"""

from pathlib import Path

from studium.domain.profiles import BOOK_TOPIC
from studium.storage.init_project import book_kind
from studium.storage.records import CLAIMS, PUBLIC_BIBLIOGRAPHY, fold_by_id

_CONFLICT_FIELDS = ("year", "title", "isbn")


def support_blockers(root: Path, source_ids: list[str]) -> list[dict[str, object]]:
    """Blockers that reject a claim. An empty list means the citation may support a draft."""

    records = _public_by_id(root)
    course_book = book_kind(root) != BOOK_TOPIC
    blockers: list[dict[str, object]] = []
    for source_id in source_ids:
        record = records.get(source_id)
        if record is None:
            blockers.append(
                {
                    "code": "claim.source_missing",
                    "entity_id": source_id,
                    "message": "no public source with that id",
                }
            )
            continue
        conflict = _conflict_blocker(record)
        if conflict is not None:
            blockers.append(conflict)
        if course_book and record.get("course_guide_cited") is not True:
            blockers.append(
                {
                    "code": "claim.not_cited",
                    "entity_id": source_id,
                    "message": "not marked as cited by the stored course guide",
                }
            )
    return blockers


def supported_drafts(root: Path) -> list[dict[str, object]]:
    """Stored drafts whose sources still pass the support check."""

    kept: list[dict[str, object]] = []
    for claim in fold_by_id(root / CLAIMS):
        if claim.get("status") != "draft":
            continue
        sources = claim.get("sources")
        if not isinstance(sources, list) or not all(isinstance(item, str) for item in sources):
            continue
        if support_blockers(root, list(sources)):
            continue
        kept.append(claim)
    return kept


def excluded_drafts(root: Path) -> list[dict[str, object]]:
    """Stored drafts that no longer pass the support check."""

    supported = {str(claim.get("id")) for claim in supported_drafts(root)}
    return [
        claim
        for claim in fold_by_id(root / CLAIMS)
        if claim.get("status") == "draft" and str(claim.get("id")) not in supported
    ]


def evidence_blockers(root: Path) -> list[dict[str, object]]:
    """Release blockers from the bibliography and from draft claims. Does not write."""

    blockers: list[dict[str, object]] = []
    records = list(_public_by_id(root).values())
    course_book = book_kind(root) != BOOK_TOPIC
    pending = 0
    for record in records:
        if record.get("classification") == "PENDING" or record.get("authority") is None:
            pending += 1
        conflict = _conflict_blocker(record)
        if conflict is not None:
            blockers.append(conflict)
        if course_book and record.get("course_guide_cited") is not True:
            blockers.append(
                {
                    "code": "claim.not_cited",
                    "entity_id": record.get("id") if isinstance(record.get("id"), str) else None,
                    "message": "not marked as cited by the stored course guide",
                }
            )
    if pending:
        blockers.append(
            {
                "code": "verify.pending",
                "entity_id": None,
                "message": f"{pending} public sources stay DISCOVERED and PENDING with no authority",
            }
        )
    for claim in fold_by_id(root / CLAIMS):
        if claim.get("status") != "draft":
            continue
        blockers.append(
            {
                "code": "verify.draft",
                "entity_id": claim.get("id") if isinstance(claim.get("id"), str) else None,
                "message": "claim is a draft and is not verified or accepted",
            }
        )
    return blockers


def _public_by_id(root: Path) -> dict[str, dict[str, object]]:
    found: dict[str, dict[str, object]] = {}
    for record in fold_by_id(root / PUBLIC_BIBLIOGRAPHY):
        identifier = record.get("id")
        if isinstance(identifier, str):
            found[identifier] = record
    return found


def _conflict_blocker(record: dict[str, object]) -> dict[str, object] | None:
    conflicts = record.get("conflicts")
    if not isinstance(conflicts, list) or not conflicts:
        return None
    fields: list[str] = []
    for item in conflicts:
        if not isinstance(item, dict):
            continue
        field = item.get("field")
        if field in _CONFLICT_FIELDS and field not in fields:
            fields.append(str(field))
    label = "stored " + ", ".join(fields) + " conflict" if fields else "stored citation conflict"
    identifier = record.get("id")
    return {
        "code": "claim.conflict",
        "entity_id": identifier if isinstance(identifier, str) else None,
        "message": f"{label}; classification stays PENDING",
    }
