"""Exercises depend on the discipline: a history book is practised with commentary, not arithmetic."""

import pytest
from test_render_regression import _explode, _open_source, _project

from studium.authoring.exercises import (
    CHRONOLOGY,
    DISCURSIVE_TYPES,
    PROFILE_DISCURSIVE_TYPES,
    allowed_types,
    numeric_allowed,
)
from studium.authoring.render import render_draft
from studium.mcp.server import dispatch

_TEXT_A = (
    "Los Reyes Católicos tomaron Granada el 2 de enero de 1492. "
    "El mismo año Colón partió de Palos y los judíos fueron expulsados."
)
_TEXT_B = "En 1492 terminó la guerra de Granada, que había comenzado en 1482, y se firmaron las Capitulaciones de Santa Fe."
_POEM = "Nuestras vidas son los ríos\nque van a dar en la mar,\nque es el morir."


def _book(tmp_path, monkeypatch, profile="HUMANITIES"):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _project(tmp_path, profile=profile)
    dispatch("studium_blueprint_store", {"sections": [{"id": "reyes", "title": "Los Reyes Católicos"}]}, session=session)
    one = _open_source(session, "Fuente A", "https://open.example/a", _TEXT_A)
    two = _open_source(session, "Fuente B", "https://open.example/b", _TEXT_B)
    poem = _open_source(session, "Coplas", "https://open.example/coplas", _POEM)
    return session, root, one, two, poem


def _record(session, **extra):
    arguments = {"section": "reyes", "prompt": "Explique la importancia de 1492."} | extra
    return dispatch("studium_problem_record", arguments, session=session)


def _answer(one, two):
    return {
        "summary": "1492 reúne la toma de Granada, el viaje de Colón y la expulsión de los judíos.",
        "sections": [
            {
                "label": "Hechos",
                "points": [
                    {"text": "Granada cae el 2 de enero de 1492.", "excerpts": [one]},
                    {"text": "La guerra de Granada había empezado en 1482.", "excerpts": [two]},
                ],
            }
        ],
        "mistakes": ["Fechar la toma de Granada en 1942."],
    }


def test_profiles_decide_which_exercise_types_exist():
    assert not numeric_allowed("HUMANITIES") and not numeric_allowed("LAW")
    assert numeric_allowed("LIFE_SCIENCES") and numeric_allowed("STEM")
    assert "SOURCE_COMMENTARY" in allowed_types("HUMANITIES")
    assert "EXPERIMENT_DESIGN" in allowed_types("LIFE_SCIENCES")
    assert "EXPERIMENT_DESIGN" not in allowed_types("HUMANITIES")
    assert allowed_types("STEM") == frozenset()
    assert set(PROFILE_DISCURSIVE_TYPES["GENERAL"]) >= DISCURSIVE_TYPES


def test_a_history_book_refuses_a_numeric_exercise_and_names_the_types_it_takes(tmp_path, monkeypatch):
    session, _root, one, two, _poem = _book(tmp_path, monkeypatch)
    refused = _record(session, expected="3", excerpts=[one, two], role="worked")
    assert refused["status"] == "problem.numeric_not_for_discipline", refused
    assert "SOURCE_COMMENTARY" in refused["message"] and "CHRONOLOGY" in refused["message"]


def test_a_development_question_is_recorded_with_a_witnessed_answer(tmp_path, monkeypatch):
    session, _root, one, two, _poem = _book(tmp_path, monkeypatch)
    stored = _record(session, problem_type="DEVELOPMENT_QUESTION", role="worked", answer=_answer(one, two))
    assert stored["status"] == "recorded", stored
    problem = stored["problem"]
    assert problem["status"] == "two_witnesses" and problem["corroboration"] == "two_witnesses"
    assert problem["kind"] == "discursive"
    checked = dispatch("studium_problem_check", {"id": problem["id"]}, session=session)
    assert checked["status"] == "two_witnesses", checked


def test_an_answer_citing_one_source_is_not_witnessed(tmp_path, monkeypatch):
    session, _root, one, _two, _poem = _book(tmp_path, monkeypatch)
    answer = _answer(one, one)
    stored = _record(session, problem_type="DEVELOPMENT_QUESTION", answer=answer)
    assert stored["problem"]["status"] == "unchecked"
    assert "corroboration" not in stored["problem"]


def test_a_type_of_another_discipline_is_refused(tmp_path, monkeypatch):
    session, _root, one, two, _poem = _book(tmp_path, monkeypatch)
    refused = _record(session, problem_type="EXPERIMENT_DESIGN", answer=_answer(one, two))
    assert refused["status"] == "problem.type_not_for_discipline", refused


def test_a_discursive_exercise_needs_an_answer_and_a_discursive_type(tmp_path, monkeypatch):
    session, _root, one, two, _poem = _book(tmp_path, monkeypatch)
    assert _record(session, problem_type="DEVELOPMENT_QUESTION")["status"] == "mcp.invalid_input"
    assert _record(session, answer=_answer(one, two))["status"] == "mcp.invalid_input"
    mixed = _record(session, problem_type="DEVELOPMENT_QUESTION", answer=_answer(one, two), expected="3")
    assert mixed["status"] == "mcp.invalid_input"


def test_every_point_must_cite_a_stored_excerpt(tmp_path, monkeypatch):
    session, _root, one, two, _poem = _book(tmp_path, monkeypatch)
    answer = _answer(one, two)
    answer["sections"][0]["points"][0]["excerpts"] = ["EXC-9999"]
    refused = _record(session, problem_type="DEVELOPMENT_QUESTION", answer=answer)
    assert refused["status"] == "claim.excerpt_missing", refused
    answer["sections"][0]["points"][0].pop("excerpts")
    assert _record(session, problem_type="DEVELOPMENT_QUESTION", answer=answer)["status"] == "mcp.invalid_input"


def test_a_commentary_quote_must_be_verbatim_in_its_excerpt(tmp_path, monkeypatch):
    session, _root, _one, two, poem = _book(tmp_path, monkeypatch)
    answer = _answer(poem, two)
    good = _record(
        session,
        problem_type="TEXT_COMMENTARY",
        source={"excerpt": poem, "quote": _POEM, "author": "Jorge Manrique", "work": "Coplas", "date": "c. 1476"},
        questions=["¿Qué metáfora organiza el pasaje?"],
        answer=answer,
    )
    assert good["status"] == "recorded", good
    forged = _record(
        session,
        problem_type="TEXT_COMMENTARY",
        source={"excerpt": poem, "quote": "Nuestras vidas son los lagos que van a dar en el mar"},
        answer=answer,
    )
    assert forged["status"] == "problem.source_not_quoted", forged
    missing = _record(session, problem_type="TEXT_COMMENTARY", answer=answer)
    assert missing["status"] == "mcp.invalid_input"


def test_a_chronology_date_must_appear_in_the_excerpt_it_cites(tmp_path, monkeypatch):
    session, _root, one, two, _poem = _book(tmp_path, monkeypatch)
    events = [
        {"date": "1482", "text": "Empieza la guerra de Granada.", "excerpts": [two]},
        {"date": "2 de enero de 1492", "text": "Los Reyes toman Granada.", "excerpts": [one]},
        {"date": "1492", "text": "Capitulaciones de Santa Fe.", "excerpts": [two]},
    ]
    stored = _record(session, problem_type=CHRONOLOGY, answer={"events": events})
    assert stored["status"] == "recorded", stored
    assert stored["problem"]["answer"]["events"][1]["year"] == 1492
    events[0] = {"date": "1481", "text": "Empieza la guerra de Granada.", "excerpts": [two]}
    refused = _record(session, problem_type=CHRONOLOGY, answer={"events": events})
    assert refused["status"] == "problem.date_not_in_excerpt", refused
    too_short = _record(session, problem_type=CHRONOLOGY, answer={"events": events[1:]})
    assert too_short["status"] == "mcp.invalid_input"


def test_the_next_step_for_a_history_book_asks_for_a_discursive_exercise(tmp_path, monkeypatch):
    _session, _root, _one, _two, _poem = _book(tmp_path, monkeypatch)
    from studium.authoring import book_next

    assert not book_next._worked_ok(_root, "reyes")
    text = book_next._discursive_types(_root)
    assert "SOURCE_COMMENTARY" in text and "CHRONOLOGY" in text


def test_a_witnessed_discursive_exercise_counts_as_the_worked_problem(tmp_path, monkeypatch):
    session, root, one, two, _poem = _book(tmp_path, monkeypatch)
    from studium.authoring import book_next

    _record(session, problem_type="DEVELOPMENT_QUESTION", role="worked", answer=_answer(one, two))
    assert book_next._worked_ok(root, "reyes")
    practice_only = dispatch("studium_problem_remove", {"id": "PRB-0001"}, session=session)
    assert practice_only["status"] == "removed"
    _record(session, problem_type="DEVELOPMENT_QUESTION", role="practice", answer=_answer(one, two))
    assert not book_next._worked_ok(root, "reyes")


def test_a_life_science_book_takes_numeric_and_discursive_exercises(tmp_path, monkeypatch):
    session, _root, one, two, _poem = _book(tmp_path, monkeypatch, profile="LIFE_SCIENCES")
    design = _record(
        session,
        problem_type="EXPERIMENT_DESIGN",
        answer={"sections": [{"label": "Control", "points": [
            {"text": "Un grupo sin tratamiento.", "excerpts": [one]},
            {"text": "Un segundo grupo con el tratamiento.", "excerpts": [two]},
        ]}]},
    )
    assert design["status"] == "recorded", design
    numeric = _record(session, expected="3", excerpts=[one, two], role="worked")
    assert numeric["status"] == "recorded", numeric


def test_the_book_prints_the_source_text_the_questions_and_the_model_answer(tmp_path, monkeypatch):
    session, root, one, two, poem = _book(tmp_path, monkeypatch)
    dispatch(
        "studium_paragraph_record",
        {"section": "reyes", "text": "La toma de Granada culmina la Reconquista.", "excerpts": [one, two]},
        session=session,
    )
    assert _record(
        session,
        problem_type="TEXT_COMMENTARY",
        role="practice",
        prompt="Comente el fragmento: localización, tema, estructura y recursos.",
        source={"excerpt": poem, "quote": _POEM, "author": "Jorge Manrique", "work": "Coplas"},
        questions=["¿Qué metáfora organiza el pasaje?"],
        answer=_answer(poem, two),
    )["status"] == "recorded"
    assert _record(
        session,
        problem_type=CHRONOLOGY,
        role="worked",
        prompt="Ordene los hechos.",
        answer={"events": [
            {"date": "1492", "text": "Capitulaciones de Santa Fe.", "excerpts": [two]},
            {"date": "1482", "text": "Empieza la guerra de Granada.", "excerpts": [two]},
            {"date": "2 de enero de 1492", "text": "Toman Granada.", "excerpts": [one]},
        ]},
    )["status"] == "recorded"
    render_draft(root)
    tex = (root / "latex" / "draft.tex").read_text(encoding="utf-8")
    assert "Ejercicio resuelto" in tex and "Pauta de respuesta" in tex
    assert "Comentario de texto" in tex and "Cronología" in tex
    assert r"Nuestras vidas son los ríos \\ que van a dar en la mar" in tex
    assert tex.index("Empieza la guerra de Granada") < tex.index("Toman Granada")
    assert "Problema resuelto" not in tex
    assert "Jorge Manrique, Coplas" in tex


@pytest.mark.parametrize("profile", ["HUMANITIES", "LAW"])
def test_no_numeric_profile_is_a_discursive_profile(profile):
    assert not numeric_allowed(profile)
    assert "NUMERICAL" not in allowed_types(profile)


def test_a_comparative_exercise_with_an_answer_is_discursive_and_without_one_is_numeric(tmp_path, monkeypatch):
    session, _root, one, two, _poem = _book(tmp_path, monkeypatch, profile="LIFE_SCIENCES")
    comparison = _record(session, problem_type="COMPARATIVE", answer=_answer(one, two))
    assert comparison["status"] == "recorded", comparison
    assert comparison["problem"]["kind"] == "discursive"
    numeric = _record(session, problem_type="COMPARATIVE", expected="3", excerpts=[one, two])
    assert numeric["problem"]["kind"] == "numeric"


def test_a_comparative_exercise_with_an_answer_is_accepted_in_a_history_book(tmp_path, monkeypatch):
    session, _root, one, two, _poem = _book(tmp_path, monkeypatch)
    assert _record(session, problem_type="COMPARATIVE", answer=_answer(one, two))["status"] == "recorded"


def test_a_history_book_reader_guide_speaks_of_an_exercise_not_a_problem(tmp_path, monkeypatch):
    _session, root, _one, _two, _poem = _book(tmp_path, monkeypatch)
    render_draft(root)
    tex = (root / "latex" / "draft.tex").read_text(encoding="utf-8")
    assert "el ejercicio resuelto" in tex
    assert "el problema resuelto" not in tex
