"""Authority checks that intake must not skip.

``origin`` is not an input. A class and a scientific axis are assigned only
when an audit asks for them.
"""

from studium.domain.enums import SOURCE_CLASSES, SOURCE_ORIGINS

_FORBIDDEN = frozenset({"ACCEPTED", "VERIFIED", "verified", "accepted"})
_MAXIMAL_CLASSES = frozenset({"A0", "A1", "A3"})
_WUOLAH_BLOCKED = frozenset({"A0", "A1", "A2", "A3"})


def source_class_error(value: str) -> str | None:
    if value in _FORBIDDEN:
        return "sources.acceptance_forbidden"
    if value in SOURCE_ORIGINS:
        return "sources.origin_is_not_authority"
    if value not in SOURCE_CLASSES:
        return "sources.class_invalid"
    return None


def authority_assignment_error(
    *,
    source_class: str | None,
    scientific_authority: str | None,
    peer_reviewed: bool | None,
    probable_kind: str | None,
) -> str | None:
    if probable_kind == "wuolah":
        if scientific_authority == "maximal" or source_class in _WUOLAH_BLOCKED:
            return "sources.authority_not_allowed"
    if scientific_authority != "maximal":
        return None
    if source_class in _MAXIMAL_CLASSES:
        return None
    if source_class == "A2" and peer_reviewed is True:
        return None
    return "sources.authority_not_allowed"
