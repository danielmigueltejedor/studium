"""Read-time migration from the stage 0 boolean to ``local_sources``.

The boolean meant "the ``--sources`` path was missing". It was not a user
decision. ``schema_version`` stays ``1.0.0``.
"""

from datetime import UTC, datetime

from studium.domain.enums import LOCAL_SOURCE_STATUSES

_ZERO_COUNT = frozenset({"UNKNOWN", "NONE", "AVAILABLE", "SKIPPED"})


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def initial_local_sources(status: str, now: str | None = None) -> dict[str, object]:
    if status not in LOCAL_SOURCE_STATUSES:
        raise ValueError("sources.status_invalid")
    return {
        "status": status,
        "prompted": False,
        "source_count": 0,
        "last_updated": utc_now() if now is None else now,
    }


def migrate_state(
    document: dict[str, object],
    *,
    labeled: bool,
    now: str | None = None,
) -> tuple[dict[str, object], bool]:
    """Return the state document and whether it differs from ``document``.

    When ``local_sources`` is already present it wins, and a leftover boolean
    is dropped. ``NONE`` and ``SKIPPED`` are never invented here.
    """

    migrated = dict(document)
    local_source_value = document.get("local_sources")
    if isinstance(local_source_value, dict):
        local = _normalize_object(dict(local_source_value))
        changed = local != local_source_value
        migrated["local_sources"] = local
        if "local_sources_missing" in migrated:
            del migrated["local_sources_missing"]
            changed = True
        return migrated, changed

    if "local_sources_missing" not in document:
        return migrated, False

    missing = document.get("local_sources_missing")
    if missing is True:
        status = "UNKNOWN"
    elif missing is False and labeled:
        status = "AVAILABLE"
    else:
        status = "UNKNOWN"
    del migrated["local_sources_missing"]
    migrated["local_sources"] = initial_local_sources(status, now or utc_now())
    return migrated, True


def _normalize_object(local: dict[str, object]) -> dict[str, object]:
    if "source_count" in local:
        count = local["source_count"]
    elif "count" in local:
        count = local["count"]
    else:
        count = 0
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        count = 0
    status = local.get("status")
    if status not in LOCAL_SOURCE_STATUSES:
        status = "UNKNOWN"
    prompted = local.get("prompted") is True
    if status == "IMPORTED" and count < 1:
        status = "AVAILABLE"
    if status in _ZERO_COUNT:
        count = 0 if status != "IMPORTED" else count
    if status != "IMPORTED":
        count = 0
    last_updated = local.get("last_updated")
    if not isinstance(last_updated, str) or not last_updated:
        last_updated = utc_now()
    return {
        "status": status,
        "prompted": prompted,
        "source_count": count,
        "last_updated": last_updated,
    }
