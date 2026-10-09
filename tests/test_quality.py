"""Labelled chapter-quality assessment: teachable, adequate, needs_work."""

from studium.mcp.server import dispatch, open_workspace, tool_names


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


def _source(session, url: str) -> str:
    recorded = dispatch("studium_public_source_record", {"title": "Open page", "url": url}, session=session)
    assert recorded["status"] == "recorded"
    return str(recorded["candidate"]["id"])


def _excerpt(session, source_id: str, url: str, text: str = "An opened page states a stored fact.") -> str:
    recorded = dispatch("studium_excerpt_record", {"source_id": source_id, "url": url, "text": text}, session=session)
    assert recorded["status"] == "recorded"
    return str(recorded["excerpt"]["id"])


def _section(session) -> None:
    assert (
        dispatch("studium_blueprint_store", {"sections": [{"id": "tema-1", "title": "Topic"}]}, session=session)["status"]
        == "recorded"
    )


def _paragraph(session, role: str, text: str, excerpts: list[str]) -> str:
    recorded = dispatch(
        "studium_paragraph_record",
        {"section": "tema-1", "role": role, "text": text, "excerpts": excerpts},
        session=session,
    )
    assert recorded["status"] == "recorded"
    return str(recorded["paragraph"]["id"])


def _audit(session, target: str, excerpts: list[str] | None = None, computation: str | None = None) -> None:
    arguments: dict[str, object] = {"target": target, "kind": "historical"}
    if excerpts is not None:
        arguments["excerpts"] = excerpts
    if computation is not None:
        arguments["computation"] = computation
    recorded = dispatch("studium_audit_record", arguments, session=session)
    assert recorded["status"] == "recorded", recorded


def _quality(session) -> dict[str, object]:
    return dispatch("studium_quality_assess", {"section": "tema-1"}, session=session)


def test_empty_section_is_needs_work(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, _root = _topic(tmp_path, "empty")
    _section(session)
    source = _source(session, "https://open.example/one")
    _excerpt(session, source, "https://open.example/one")
    assert "studium_quality_assess" in tool_names()
    quality = _quality(session)
    assert quality["status"] == "ok"
    assessment = quality["assessment"]
    assert assessment["label"] == "needs_work"
    assert assessment["failures"] >= 1
    labels = {check["label"] for check in assessment["checks"]}
    assert labels <= {"PASS", "WARN", "FAIL"}
    checks = {check["check"]: check for check in assessment["checks"]}
    assert checks["lead"]["label"] == "FAIL"
    assert checks["worked_problem"]["label"] == "FAIL"
    assert checks["self_check"]["label"] == "FAIL"


def test_complete_teachible_chapter_is_teachable(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, _root = _topic(tmp_path, "full")
    _section(session)
    left = _excerpt(session, _source(session, "https://open.example/one"), "https://open.example/one")
    right = _excerpt(session, _source(session, "https://open.example/two"), "https://open.example/two")
    sentence = "The chapter teaches this point from the opened page in the writer's own words."
    explanation = " ".join([sentence] * 16)
    lead = " ".join([sentence] * 4)
    advice = " ".join(["Keep the later point tied to the opened page and write it in the chapter's own sentences."] * 3)
    purpose = _paragraph(session, "purpose", lead, [left])
    first = _paragraph(session, "explanation", explanation, [left])
    second = _paragraph(session, "explanation", explanation + " The next point follows.", [right])
    tip = _paragraph(session, "consejo", advice, [left])
    _paragraph(session, "self_check", "Name the point the opened page supports in your own words.", [left])
    witnessed = dispatch(
        "studium_problem_record",
        {"section": "tema-1", "prompt": "What do the two pages report?", "expected": "4", "excerpts": [left, right]},
        session=session,
    )
    assert witnessed["problem"]["status"] == "two_witnesses"
    for target in (purpose, first, second, tip):
        _audit(session, target, excerpts=[left, right])
    quality = _quality(session)
    assessment = quality["assessment"]
    assert assessment["label"] == "teachable", assessment
    assert assessment["failures"] == 0
    assert assessment["warnings"] == 0
    for check in assessment["checks"]:
        assert check["label"] == "PASS", check


def test_single_source_is_adequate_not_teachable(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, _root = _topic(tmp_path, "one-source")
    _section(session)
    only = _excerpt(session, _source(session, "https://open.example/one"), "https://open.example/one")
    sentence = "The chapter teaches this point from the opened page in the writer's own words."
    explanation = " ".join([sentence] * 16)
    lead = " ".join([sentence] * 4)
    advice = " ".join(["Keep the later point tied to the opened page and write it in the chapter's own sentences."] * 3)
    purpose = _paragraph(session, "purpose", lead, [only])
    first = _paragraph(session, "explanation", explanation, [only])
    second = _paragraph(session, "explanation", explanation + " The next point follows.", [only])
    tip = _paragraph(session, "consejo", advice, [only])
    _paragraph(session, "self_check", "Name the point the opened page supports in your own words.", [only])
    computed = dispatch(
        "studium_computation_check",
        {"expression": "1e1 * 2", "result": 20, "section": "tema-1"},
        session=session,
    )
    assert computed["status"] == "replayed", computed
    computation_id = str(computed["computation"]["id"])
    for target in (purpose, first, second, tip):
        _audit(session, target, computation=computation_id)
    assessment = _quality(session)["assessment"]
    assert assessment["label"] == "adequate", assessment
    checks = {check["check"]: check for check in assessment["checks"]}
    assert checks["source_diversity"]["label"] == "WARN"
    assert checks["source_diversity"]["description"].startswith("the section cites")


def test_whole_book_quality_lists_every_section(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, _root = _topic(tmp_path, "whole")
    assert (
        dispatch(
            "studium_blueprint_store",
            {"sections": [{"id": "tema-1", "title": "One"}, {"id": "tema-2", "title": "Two"}]},
            session=session,
        )["status"]
        == "recorded"
    )
    quality = dispatch("studium_quality_assess", {}, session=session)
    assert quality["status"] == "ok"
    assert {item["section"] for item in quality["assessments"]} == {"tema-1", "tema-2"}
    assert all(item["label"] in {"teachable", "adequate", "needs_work"} for item in quality["assessments"])
