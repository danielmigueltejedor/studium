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
