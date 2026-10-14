"""Structured contradiction statuses: context, units, definitions, terminology."""

from studium.mcp.server import dispatch, open_workspace

_TEACH = (
    "This explanation teaches the stored quantity so a reader can follow the derivation, "
    "the comparison, and the later problem without treating the model as a source of truth."
)


def _explode(*_args, **_kwargs):
    raise AssertionError("must not fetch")


def _topic(tmp_path, slug: str):
    session = open_workspace(str(tmp_path))
    assert (
        dispatch("studium_project_create", {"slug": slug, "topic": "Mecanica de fluidos", "language": "en"}, session=session)[
            "status"
        ]
        == "created"
    )
    return session, tmp_path / slug


def _section(session, section_id: str = "tema-1", title: str = "Topic") -> None:
    assert (
        dispatch("studium_blueprint_store", {"sections": [{"id": section_id, "title": title}]}, session=session)["status"]
        == "recorded"
    )


def _source(session, url: str) -> str:
    recorded = dispatch("studium_public_source_record", {"title": "Open page", "url": url}, session=session)
    assert recorded["status"] == "recorded"
    return str(recorded["candidate"]["id"])


def _excerpt(session, source_id: str, url: str, text: str = "An opened page states a stored fact.") -> str:
    recorded = dispatch("studium_excerpt_record", {"source_id": source_id, "url": url, "text": text}, session=session)
    assert recorded["status"] == "recorded"
    return str(recorded["excerpt"]["id"])


def _two_excerpts(session) -> tuple[str, str]:
    left = _excerpt(session, _source(session, "https://open.example/one"), "https://open.example/one")
    right = _excerpt(session, _source(session, "https://open.example/two"), "https://open.example/two")
    return left, right


def _paragraph(session, section: str, text: str, excerpts: list[str]) -> str:
    recorded = dispatch("studium_paragraph_record", {"section": section, "text": text, "excerpts": excerpts}, session=session)
    assert recorded["status"] == "recorded"
    return str(recorded["paragraph"]["id"])


def _scan(session) -> dict[str, object]:
    return dispatch("studium_contradiction_scan", {}, session=session)


def test_values_under_different_stated_conditions_are_context_dependent(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, _root = _topic(tmp_path, "viscosity")
    _section(session)
    left, right = _two_excerpts(session)
    _paragraph(session, "tema-1", f"The viscosity is 1.0 at 20 °C. {_TEACH}", [left])
    _paragraph(session, "tema-1", f"The viscosity is 0.65 at 40 °C. {_TEACH}", [right])
    scanned = _scan(session)
    assert scanned["status"] == "ok"
    assert scanned["open_count"] == 0
    assert scanned["released"] is False


def test_same_condition_with_different_values_is_confirmed(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, _root = _topic(tmp_path, "viscosity")
    _section(session)
    left, right = _two_excerpts(session)
    _paragraph(session, "tema-1", f"The viscosity is 1.0 at 20 °C. {_TEACH}", [left])
    _paragraph(session, "tema-1", f"The viscosity is 0.8 at 20 °C. {_TEACH}", [right])
    scanned = _scan(session)
    assert scanned["open_count"] >= 1
    item = next(item for item in scanned["contradictions"] if item["quantity"] == "viscosity")
    assert item["verdict"] == "CONFIRMED_CONTRADICTION"
    assert item["category"] == "numeric"
    assert item["sources"]


def test_different_units_are_context_dependent_not_contradictory(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, _root = _topic(tmp_path, "density")
    _section(session)
    left, right = _two_excerpts(session)
    _paragraph(session, "tema-1", f"The density is 2 g/cm3. {_TEACH}", [left])
    _paragraph(session, "tema-1", f"The density is 2000 kg/m3. {_TEACH}", [right])
    scanned = _scan(session)
    assert scanned["status"] == "ok"
    assert scanned["open_count"] == 0
    assert scanned["contradictions"] == []


def test_only_one_condition_is_possible_contradiction(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, _root = _topic(tmp_path, "viscosity")
    _section(session)
    left, right = _two_excerpts(session)
    _paragraph(session, "tema-1", f"The viscosity is 1.0 at 20 °C. {_TEACH}", [left])
    _paragraph(session, "tema-1", f"The viscosity is 0.8. {_TEACH}", [right])
    scanned = _scan(session)
    assert scanned["open_count"] >= 1
    item = next(item for item in scanned["contradictions"] if item["quantity"] == "viscosity")
    assert item["verdict"] == "POSSIBLE_CONTRADICTION"
    assert scanned["released"] is False


def test_definition_conflict_is_confirmed(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, _root = _topic(tmp_path, "mass")
    _section(session)
    left, right = _two_excerpts(session)
    _paragraph(session, "tema-1", f"Mass is defined as a conserved quantity. {_TEACH}", [left])
    _paragraph(session, "tema-1", f"Mass is defined as a property of matter. {_TEACH}", [right])
    scanned = _scan(session)
    item = next(item for item in scanned["contradictions"] if item["category"] == "definition")
    assert item["verdict"] == "CONFIRMED_CONTRADICTION"
    assert item["quantity"] == "mass"


def test_terminology_conflict_is_confirmed(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, _root = _topic(tmp_path, "flow")
    _section(session)
    left, right = _two_excerpts(session)
    _paragraph(session, "tema-1", f"The flow is also called steady flow. {_TEACH}", [left])
    _paragraph(session, "tema-1", f"The flow is also called uniform flow. {_TEACH}", [right])
    scanned = _scan(session)
    item = next(item for item in scanned["contradictions"] if item["category"] == "terminology")
    assert item["verdict"] == "CONFIRMED_CONTRADICTION"


def test_cross_chapter_conflict_is_marked(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, _root = _topic(tmp_path, "density")
    assert (
        dispatch(
            "studium_blueprint_store",
            {"sections": [{"id": "tema-1", "title": "One"}, {"id": "tema-2", "title": "Two"}]},
            session=session,
        )["status"]
        == "recorded"
    )
    left, right = _two_excerpts(session)
    _paragraph(session, "tema-1", f"The density is 2. {_TEACH}", [left])
    _paragraph(session, "tema-2", f"The density is 9. {_TEACH}", [right])
    scanned = _scan(session)
    item = next(item for item in scanned["contradictions"] if item["quantity"] == "density")
    assert item["verdict"] == "CONFIRMED_CONTRADICTION"
    assert item["cross_chapter"] is True


def test_resolution_closes_a_previous_open_contradiction(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, _root = _topic(tmp_path, "density")
    _section(session)
    left, right = _two_excerpts(session)
    _paragraph(session, "tema-1", f"The density is 2. {_TEACH}", [left])
    second = _paragraph(session, "tema-1", f"The density is 9. {_TEACH}", [right])
    assert _scan(session)["open_count"] >= 1
    replaced = dispatch(
        "studium_paragraph_replace",
        {"id": second, "text": f"The density is 2. {_TEACH}", "excerpts": [right]},
        session=session,
    )
    assert replaced["status"] == "replaced"
    assert _scan(session)["open_count"] == 0


def _records(root):
    import json

    return [json.loads(line) for line in (root / "draft" / "contradictions.jsonl").read_text().splitlines() if line.strip()]


def _current(root):
    from studium.storage.records import CONTRADICTIONS, fold_by_id

    return [item for item in fold_by_id(root / CONTRADICTIONS) if item.get("id") != "scan"]


def test_reworded_contradiction_is_resolved_when_the_quantity_disappears(tmp_path, monkeypatch):
    """F35: rewording so the quantity no longer appears must close the open record."""

    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _topic(tmp_path, "beta")
    _section(session)
    left, right = _two_excerpts(session)
    _paragraph(session, "tema-1", f"In the Lorenz model beta = 8. {_TEACH}", [left])
    second = _paragraph(session, "tema-1", f"For the transport theorem beta = 1. {_TEACH}", [right])
    first_scan = _scan(session)
    assert first_scan["open_count"] == 1
    opened = first_scan["contradictions"][0]
    assert opened["quantity"] == "beta"
    blocked = dispatch("studium_book_review", {}, session=session)
    assert any("open contradiction: beta" in reason for reason in blocked["reasons"])

    replaced = dispatch(
        "studium_paragraph_replace",
        {"id": second, "text": f"For the transport theorem the intensive property is one per unit mass. {_TEACH}", "excerpts": [right]},
        session=session,
    )
    assert replaced["status"] == "replaced"
    rescanned = _scan(session)
    assert rescanned["open_count"] == 0
    resolved = [item for item in rescanned["resolved"] if item["id"] == opened["id"]]
    assert len(resolved) == 1
    assert resolved[0]["status"] == "resolved"
    assert resolved[0]["resolution"]["reason"] == "no_longer_detected"
    assert resolved[0]["resolution"]["passages_changed"] == [second]
    from studium.authoring.contradictions import open_contradictions

    assert open_contradictions(root) == []
    after = dispatch("studium_book_review", {}, session=session)
    assert not any("open contradiction" in reason for reason in after.get("reasons", []))
    # The original open record is still in the append-only history.
    history = [item for item in _records(root) if item.get("id") == opened["id"]]
    assert [item["status"] for item in history] == ["open", "resolved"]
    assert history[0]["values"] == {"1": [second], "8": [history[0]["passages"][0]]}


def test_genuine_contradiction_still_blocks_after_rescans(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _topic(tmp_path, "density")
    _section(session)
    left, right = _two_excerpts(session)
    _paragraph(session, "tema-1", f"The density is 2. {_TEACH}", [left])
    _paragraph(session, "tema-1", f"The density is 9. {_TEACH}", [right])
    first = _scan(session)
    second = _scan(session)
    third = _scan(session)
    assert first["open_count"] == second["open_count"] == third["open_count"] == 1
    assert first["contradictions"][0]["id"] == third["contradictions"][0]["id"]
    assert third["resolved"] == []
    blocked = dispatch("studium_book_review", {}, session=session)
    assert any("open contradiction: density" in reason for reason in blocked["reasons"])
    # Rescanning unchanged text does not append a new record per scan.
    assert len([item for item in _records(root) if item.get("quantity") == "density"]) == 1


def test_repeated_scans_do_not_duplicate_context_dependent_findings(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _topic(tmp_path, "viscosity")
    _section(session)
    left, right = _two_excerpts(session)
    _paragraph(session, "tema-1", f"The viscosity is 1.0 at 20 °C. {_TEACH}", [left])
    _paragraph(session, "tema-1", f"The viscosity is 0.65 at 40 °C. {_TEACH}", [right])
    for _ in range(3):
        assert _scan(session)["open_count"] == 0
    records = [item for item in _records(root) if item.get("quantity") == "viscosity"]
    assert len(records) == 1
    assert records[0]["status"] == "not_open"


def test_reclassified_contradiction_is_resolved_with_its_reason(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _topic(tmp_path, "viscosity")
    _section(session)
    left, right = _two_excerpts(session)
    _paragraph(session, "tema-1", f"The viscosity is 1.0 at 20 °C. {_TEACH}", [left])
    second = _paragraph(session, "tema-1", f"The viscosity is 0.8 at 20 °C. {_TEACH}", [right])
    opened = _scan(session)["contradictions"][0]
    dispatch(
        "studium_paragraph_replace",
        {"id": second, "text": f"The viscosity is 0.8 at 30 °C. {_TEACH}", "excerpts": [right]},
        session=session,
    )
    rescanned = _scan(session)
    assert rescanned["open_count"] == 0
    resolved = next(item for item in rescanned["resolved"] if item["id"] == opened["id"])
    assert resolved["resolution"]["reason"] == "reclassified"
    assert resolved["resolution"]["verdict"] == "CONTEXT_DEPENDENT"
    current = [item for item in _current(root) if item.get("quantity") == "viscosity"]
    assert sorted(item["status"] for item in current) == ["not_open", "resolved"]


def test_reintroduced_contradiction_reopens_the_same_record(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, _root = _topic(tmp_path, "density")
    _section(session)
    left, right = _two_excerpts(session)
    _paragraph(session, "tema-1", f"The density is 2. {_TEACH}", [left])
    second = _paragraph(session, "tema-1", f"The density is 9. {_TEACH}", [right])
    opened = _scan(session)["contradictions"][0]
    dispatch("studium_paragraph_replace", {"id": second, "text": f"The mass is 9. {_TEACH}", "excerpts": [right]}, session=session)
    assert _scan(session)["open_count"] == 0
    dispatch("studium_paragraph_replace", {"id": second, "text": f"The density is 7. {_TEACH}", "excerpts": [right]}, session=session)
    reopened = _scan(session)
    assert reopened["open_count"] == 1
    assert reopened["contradictions"][0]["id"] == opened["id"]
    assert reopened["contradictions"][0]["values"] == {"2": [reopened["contradictions"][0]["passages"][0]], "7": [second]}


def test_legacy_stale_open_records_are_resolved_by_a_fresh_scan(tmp_path, monkeypatch):
    """F35 as stored by book-01: open records with no passage hashes and duplicate not_open rows."""

    import json

    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _topic(tmp_path, "legacy")
    _section(session)
    left, right = _two_excerpts(session)
    _paragraph(session, "tema-1", f"The viscosity is 1.0 at 20 °C. {_TEACH}", [left])
    _paragraph(session, "tema-1", f"The viscosity is 0.65 at 40 °C. {_TEACH}", [right])
    path = root / "draft" / "contradictions.jsonl"
    legacy = [
        {"schema_version": "1.0.0", "id": "CON-0901", "quantity": "beta", "values": {"1": ["PAR-0124"], "8": ["PAR-0021"]},
         "passages": ["PAR-0021", "PAR-0124"], "status": "open", "verdict": "CONFIRMED_CONTRADICTION", "category": "numeric",
         "detail": "the passages assign different values to the same quantity", "sources": [], "cross_chapter": True,
         "recorded_at": "2026-10-14T14:37:49Z"},
        {"schema_version": "1.0.0", "id": "CON-0902", "quantity": "viscosity", "values": {}, "passages": [], "status": "not_open",
         "verdict": "CONTEXT_DEPENDENT", "category": "numeric", "detail": "", "sources": [], "cross_chapter": False,
         "recorded_at": "2026-10-14T14:37:49Z"},
    ]
    with path.open("a") as handle:
        for item in legacy:
            handle.write(json.dumps(item) + "\n")
    from studium.authoring.contradictions import open_contradictions

    assert [item["id"] for item in open_contradictions(root)] == ["CON-0901"]
    scanned = _scan(session)
    assert scanned["open_count"] == 0
    resolved = next(item for item in scanned["resolved"] if item["id"] == "CON-0901")
    assert resolved["resolution"]["reason"] == "no_longer_detected"
    assert resolved["resolution"]["passages_changed"] == ["PAR-0021", "PAR-0124"]
    assert open_contradictions(root) == []
    # The context-dependent finding reuses the legacy not_open row instead of adding another.
    viscosity = [item for item in _current(root) if item.get("quantity") == "viscosity"]
    assert [item["id"] for item in viscosity] == ["CON-0902"]
