"""Project-local stable identifiers.

Counters only grow. An issued id is never reused.
"""

from collections.abc import Mapping
from types import MappingProxyType

PREFIXES: frozenset[str] = frozenset(
    {
        "SRC",
        "EVD",
        "CLM",
        "PAR",
        "PRB",
        "CON",
        "SYM",
        "TRM",
        "EQ",
        "DER",
        "FIG",
        "EX",
        "CH",
        "REV",
        "TSK",
        "TOP",
        "OUT",
        "SKL",
        "CNF",
        "WAV",
        "CST",
        "VRF",
    }
)


class IdAllocator:
    """Pure allocator. ``allocate`` returns the new id and a new allocator."""

    def __init__(self, counters: Mapping[str, int] | None = None) -> None:
        raw = {} if counters is None else dict(counters)
        for prefix, count in raw.items():
            if prefix not in PREFIXES:
                raise ValueError("id.unknown_prefix")
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ValueError("id.counter_invalid")
        self._counters: Mapping[str, int] = MappingProxyType(raw)

    @property
    def counters(self) -> Mapping[str, int]:
        return self._counters

    def allocate(self, prefix: str) -> tuple[str, "IdAllocator"]:
        if prefix not in PREFIXES:
            raise ValueError("id.unknown_prefix")
        current = self._counters.get(prefix, 0)
        issued = current + 1
        if issued <= current:
            raise ValueError("id.counter_invalid")
        width = max(4, len(str(issued)))
        identifier = f"{prefix}-{issued:0{width}d}"
        updated = dict(self._counters)
        updated[prefix] = issued
        return identifier, IdAllocator(updated)
