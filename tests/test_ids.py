import re

import pytest

from studium.domain.ids import PREFIXES, IdAllocator

_ID_RE = re.compile(
    r"^(SRC|EVD|CLM|PAR|PRB|CON|SYM|TRM|EQ|DER|FIG|EX|CH|REV|TSK|TOP|OUT|SKL|CNF|WAV|CST|VRF)-[0-9]{4,}$"
)


def test_allocates_src_0001_then_src_0002():
    allocator = IdAllocator()
    first, allocator = allocator.allocate("SRC")
    second, allocator = allocator.allocate("SRC")
    assert first == "SRC-0001"
    assert second == "SRC-0002"
    assert _ID_RE.fullmatch(first)
    assert _ID_RE.fullmatch(second)
    assert allocator.counters["SRC"] == 2


def test_counter_does_not_go_backwards():
    start = IdAllocator({"SRC": 2, "TSK": 1})
    issued, nxt = start.allocate("SRC")
    assert issued == "SRC-0003"
    assert start.counters["SRC"] == 2
    assert nxt.counters["SRC"] == 3
    assert nxt.counters["TSK"] == 1

    again, later = nxt.allocate("SRC")
    assert again == "SRC-0004"
    assert later.counters["SRC"] > nxt.counters["SRC"]

    task, after = later.allocate("TSK")
    assert task == "TSK-0002"
    assert after.counters["SRC"] == 4
    assert after.counters["TSK"] == 2


def test_width_grows_past_four_digits():
    issued, allocator = IdAllocator({"SRC": 9999}).allocate("SRC")
    assert issued == "SRC-10000"
    assert _ID_RE.fullmatch(issued)
    assert allocator.counters["SRC"] == 10000


def test_every_prefix_allocates_a_stable_id():
    allocator = IdAllocator()
    for prefix in sorted(PREFIXES):
        issued, allocator = allocator.allocate(prefix)
        assert issued == f"{prefix}-0001"
        assert _ID_RE.fullmatch(issued)


def test_unknown_prefix_raises_value_error():
    with pytest.raises(ValueError, match=r"id\.unknown_prefix"):
        IdAllocator().allocate("NOPE")
    with pytest.raises(ValueError, match=r"id\.unknown_prefix"):
        IdAllocator({"NOPE": 1})
