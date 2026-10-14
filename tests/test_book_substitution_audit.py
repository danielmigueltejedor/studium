"""Tests for non-destructive book substitution inventories."""

from copy import deepcopy
from pathlib import Path

from studium.authoring.book_substitution_audit import (
    audit_book_substitutions,
)
from studium.authoring.problems import _solution


def _sample():
    normalized, error = _solution({
        "given": [
            {"symbol": "V1", "value": "1", "unit": "m/s"},
            {"symbol": "D1", "value": "0.2", "unit": "m"},
            {"symbol": "D2", "value": "0.1", "unit": "m"},
        ],
        "model": [{
            "name": "Continuity",
            "latex": r"V_2=V_1(D_1/D_2)^2",
            "symbolic": "V1*(D1*D1)/(D2*D2)",
        }],
    })

    assert error is None
    assert normalized is not None

    return [
        {"id": "PRB-0001", "solution": normalized},
        {"id": "PRB-0002", "solution": {}},
        {"id": "PRB-0003"},
    ]


def _install(monkeypatch, records):
    monkeypatch.setattr(
        "studium.authoring.book_substitution_audit.list_problems",
        lambda root: {"status": "ok", "problems": records},
    )


def test_full_inventory(monkeypatch):
    _install(monkeypatch, _sample())

    result = audit_book_substitutions(Path("."))

    assert result["status"] == "ok"
    assert result["total_problems"] == 3
    assert result["examined"] == 3
    assert result["next_offset"] is None
    assert result["summary"] == {
        "match": 1,
        "missing": 1,
        "no_structured_solution": 1,
    }


def test_pagination(monkeypatch):
    _install(monkeypatch, _sample())

    first = audit_book_substitutions(Path("."), limit=2)
    second = audit_book_substitutions(
        Path("."),
        offset=first["next_offset"],
        limit=2,
    )

    assert first["examined"] == 2
    assert first["next_offset"] == 2
    assert second["examined"] == 1
    assert second["next_offset"] is None


def test_inventory_never_changes_original_records(monkeypatch):
    records = _sample()
    original = deepcopy(records)
    _install(monkeypatch, records)

    audit_book_substitutions(Path("."))

    assert records == original


def test_invalid_pagination_is_rejected():
    for offset, limit in [
        (-1, 30),
        (True, 30),
        (0, 0),
        (0, 51),
        (0, True),
    ]:
        result = audit_book_substitutions(
            Path("."),
            offset=offset,
            limit=limit,
        )

        assert result["status"] == "mcp.invalid_input"


def test_review_item_includes_original_and_candidate(monkeypatch):
    records = _sample()
    records[0]["solution"]["substitution"] = (
        r"\frac{0.2\,\mathrm{m}^{2}}"
        r"{0.1\,\mathrm{m}^{2}}"
    )

    _install(monkeypatch, records)

    result = audit_book_substitutions(Path("."))
    item = result["items"][0]

    assert item["classification"] == "requires_review"
    assert item["stored"] != item["candidate"]
    assert result["stored_content_modified"] is False
