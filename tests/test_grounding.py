"""The math-grounding model: sources, justified deductions, and numeric examples.

A prose formula is grounded by a cited excerpt, by a stored verified derivation,
or by a replayed computation. A paragraph may also declare that grounding
explicitly; the server revalidates every declaration and rejects one it cannot
ground. None of this marks a passage verified or accepted.
"""

import json

from studium.mcp.server import dispatch, open_workspace


def test_verified_derivation_grounds_a_prose_formula(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, _root = _book(tmp_path)
    excerpt = _excerpt(session, "La presión es fuerza por unidad de área.")
    derivation = _derivation(session, "p = F / A")
    _check_numeric(session, derivation, "F / A", {"F": 100, "A": 2}, 50)
    text = "La presión en un punto cumple p = F / A y se mide en pascales."
    recorded = dispatch(
        "studium_paragraph_record",
        {"section": "presion", "text": text, "excerpts": [excerpt]},
        session=session,
    )
    assert recorded["status"] == "recorded"
    report = dispatch("studium_quality_report", {}, session=session)
    grounding = report["math_grounding"]
    assert grounding["formulas"] == 1
    assert grounding["formulas_ungrounded"] == 0
    # The derivation's only check is numeric: the equation is numerically reproduced, not symbolically verified.
    assert grounding["by_status"]["numerically_reproduced"] == 1
    assert grounding["checked_derivations"] == 1
    assert grounding_draft_not_released(recorded)
    assert "verified" not in json.dumps(recorded).lower().replace("not verified", "")


def test_derivation_without_a_passing_check_does_not_ground(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, _root = _book(tmp_path)
    excerpt = _excerpt(session, "La presión es fuerza por unidad de área.")
    _derivation(session, "p = F / A")  # recorded but never checked
    text = "La presión en un punto cumple p = F / A y se mide en pascales."
    paragraph = dispatch(
        "studium_paragraph_record",
        {"section": "presion", "text": text, "excerpts": [excerpt]},
        session=session,
    )
    assert paragraph["status"] == "recorded"
    report = dispatch("studium_quality_report", {}, session=session)
    assert report["math_grounding"]["formulas_ungrounded"] == 1
    audit = dispatch(
        "studium_audit_record",
        {"target": paragraph["paragraph"]["id"], "kind": "formula", "excerpts": _two(session)},
        session=session,
    )
    assert audit["status"] == "audit.rejected"
    assert "checked derivation" in audit["message"]


def test_declared_derivation_is_revalidated(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, _root = _book(tmp_path)
    excerpt = _excerpt(session, "La presión es fuerza por unidad de área.")
    derivation = _derivation(session, "p = F / A")
    _check_numeric(session, derivation, "F / A", {"F": 100, "A": 2}, 50)
    good = dispatch(
        "studium_paragraph_record",
        {
            "section": "presion",
            "text": "La presión es una fuerza repartida sobre un área.",
            "excerpts": [excerpt],
            "math": [{"statement": "p = F / A", "kind": "derivation", "refs": [derivation]}],
        },
        session=session,
    )
    assert good["status"] == "recorded"
    assert good["paragraph"]["math"][0]["kind"] == "derivation"
    bogus = dispatch(
        "studium_paragraph_record",
        {
            "section": "presion",
            "text": "Otra explicación del mismo fenómeno físico.",
            "excerpts": [excerpt],
            "math": [{"statement": "p = F * A", "kind": "derivation", "refs": [derivation]}],
        },
        session=session,
    )
    assert bogus["status"] == "paragraph.math_ungrounded"


def test_declared_example_is_bound_to_a_replayed_computation(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, _root = _book(tmp_path)
    excerpt = _excerpt(session, "El agua tiene densidad 1000.")
    computed = dispatch(
        "studium_computation_check",
        {"expression": "1000 * 9.81 * 10", "result": 98100, "section": "presion"},
        session=session,
    )
    computation = computed["computation"]["id"]
    good = dispatch(
        "studium_paragraph_record",
        {
            "section": "presion",
            "text": "El agua a diez metros de profundidad ejerce presión.",
            "excerpts": [excerpt],
            "math": [{"statement": "p = 98100", "kind": "example", "refs": [computation]}],
        },
        session=session,
    )
    assert good["status"] == "recorded"
    assert good["paragraph"]["math"][0]["kind"] == "example"
    fabricated = dispatch(
        "studium_paragraph_record",
        {
            "section": "presion",
            "text": "El agua a diez metros ejerce otra presión.",
            "excerpts": [excerpt],
            "math": [{"statement": "p = 55555", "kind": "example", "refs": [computation]}],
        },
        session=session,
    )
    assert fabricated["status"] == "paragraph.math_ungrounded"


def test_declared_source_must_be_quoted_by_a_cited_excerpt(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, _root = _book(tmp_path)
    excerpt = _excerpt(session, "La presión es fuerza por unidad de área.")
    quoted = dispatch(
        "studium_paragraph_record",
        {
            "section": "presion",
            "text": "La presión es fuerza por unidad de área, como dice la fuente.",
            "excerpts": [excerpt],
            "math": [{"statement": "presión = fuerza / área", "kind": "source", "refs": [excerpt]}],
        },
        session=session,
    )
    assert quoted["status"] == "paragraph.math_ungrounded"
    other = _excerpt(session, "El caudal es volumen por unidad de tiempo.", url="https://open.example/q")
    unknown = dispatch(
        "studium_paragraph_record",
        {
            "section": "presion",
            "text": "La presión se define de forma precisa.",
            "excerpts": [excerpt],
            "math": [{"statement": "q = V / t", "kind": "source", "refs": [other]}],
        },
        session=session,
    )
    assert unknown["status"] == "paragraph.math_ungrounded"


def test_declaration_survives_replace_and_change_drops_it(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, _root = _book(tmp_path)
    excerpt = _excerpt(session, "La presión es fuerza por unidad de área.")
    derivation = _derivation(session, "p = F / A")
    _check_numeric(session, derivation, "F / A", {"F": 100, "A": 2}, 50)
    recorded = dispatch(
        "studium_paragraph_record",
        {
            "section": "presion",
            "text": "La presión es una fuerza repartida sobre un área.",
            "excerpts": [excerpt],
            "math": [{"statement": "p = F / A", "kind": "derivation", "refs": [derivation]}],
        },
        session=session,
    )
    identifier = recorded["paragraph"]["id"]
    replaced = dispatch(
        "studium_paragraph_replace",
        {"id": identifier, "text": "La presión reparte una fuerza sobre un área.", "excerpts": [excerpt]},
        session=session,
    )
    assert replaced["status"] == "replaced"
    assert replaced["paragraph"]["math"][0]["refs"] == [derivation]
    dropped = dispatch(
        "studium_paragraph_replace",
        {"id": identifier, "text": "La presión reparte una fuerza sobre un área.", "excerpts": [excerpt], "math": []},
        session=session,
    )
    assert dropped["status"] == "replaced"
    assert "math" not in dropped["paragraph"]


def test_rechecked_derivation_makes_the_audit_stale(tmp_path, monkeypatch):
    from studium.authoring.audit import audited_paragraph_ids

    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, _root = _book(tmp_path)
    excerpt = _excerpt(session, "La presión es fuerza por unidad de área.")
    left = _excerpt(session, "La presión se mide en pascales.", url="https://open.example/si")
    derivation = _derivation(session, "p = F / A")
    _check_numeric(session, derivation, "F / A", {"F": 100, "A": 2}, 50)
    recorded = dispatch(
        "studium_paragraph_record",
        {
            "section": "presion",
            "text": "La presión es una fuerza repartida sobre un área.",
            "excerpts": [excerpt],
            "math": [{"statement": "p = F / A", "kind": "derivation", "refs": [derivation]}],
        },
        session=session,
    )
    audited = dispatch(
        "studium_audit_record",
        {"target": recorded["paragraph"]["id"], "kind": "formula", "excerpts": [excerpt, left]},
        session=session,
    )
    assert audited["status"] == "recorded"
    assert recorded["paragraph"]["id"] in audited_paragraph_ids(_root)
    _check_numeric(session, derivation, "F / A", {"F": 100, "A": 4}, 25)
    assert recorded["paragraph"]["id"] not in audited_paragraph_ids(_root)


def grounding_draft_not_released(payload):
    return payload.get("released") is False and payload.get("project_state") != "RELEASED"


def _book(tmp_path):
    session = open_workspace(str(tmp_path))
    assert (
        dispatch("studium_project_create", {"slug": "g", "topic": "Fluidos", "language": "es"}, session=session)["status"]
        == "created"
    )
    assert (
        dispatch(
            "studium_blueprint_store",
            {"sections": [{"id": "presion", "title": "Presión"}]},
            session=session,
        )["status"]
        == "recorded"
    )
    return session, tmp_path / "g"


def _excerpt(session, text, url="https://open.example/p"):
    source = dispatch("studium_public_source_record", {"title": "Open", "url": url}, session=session)
    source_id = source["candidate"]["id"] if "candidate" in source else source["source"]["id"]
    recorded = dispatch("studium_excerpt_record", {"source_id": source_id, "url": url, "text": text}, session=session)
    assert recorded["status"] == "recorded"
    return str(recorded["excerpt"]["id"])


def _two(session):
    return [
        _excerpt(session, "El agua tiene densidad 1000.", url="https://open.example/one"),
        _excerpt(session, "La presión se mide en pascales.", url="https://open.example/si"),
    ]


def _derivation(session, equation):
    recorded = dispatch("studium_derivation_record", {"section": "presion", "name": "Presión", "equation": equation}, session=session)
    assert recorded["status"] == "recorded"
    return str(recorded["derivation"]["id"])


def _check_numeric(session, derivation, expression, values, claimed):
    checked = dispatch(
        "studium_derivation_check",
        {"id": derivation, "numeric": {"expression": expression, "values": values, "claimed": claimed}},
        session=session,
    )
    assert checked["status"] == "checked"


def _explode(*_args, **_kwargs):
    raise AssertionError("must not fetch")
