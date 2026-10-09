"""Structured mathematics, structured solutions, and the depth/length verdict.

Every assertion follows from what the pipeline actually stores, checks, and
renders. The point of these tests is to keep the book's mathematics typeset
rather than printing the raw arithmetic the verifier replays.
"""

import pytest

from studium.authoring.depth.length import assess_length_match, estimate_book_scope
from studium.authoring.depth.profiles import PROFILES
from studium.authoring.mathematics import (
    MathError,
    substitution_latex,
    symbol_names_of,
    symbolic_latex,
    unit_latex,
    validate_latex,
)
from studium.authoring.problems import EXERCISE_DIFFICULTIES, PROBLEM_TYPES
from studium.mcp.server import dispatch, open_workspace

_COURSE = {
    "course": "Mecánica de Fluidos",
    "university": "Universidad de León",
    "degree": "Grado en Ingeniería Aeroespacial",
    "language": "es",
    "profile": "STEM",
}


def _project(tmp_path, slug="fluidos-math"):
    session = open_workspace(str(tmp_path))
    created = dispatch("studium_project_create", {"slug": slug, **_COURSE}, session=session)
    assert created["status"] == "created", created
    return session, tmp_path / slug


def _open_source(session, title, url, text):
    record = dispatch(
        "studium_public_source_record",
        {"title": title, "url": url, "text": text},
        session=session,
    )
    assert record["status"] == "recorded", record
    source_id = record["candidate"]["id"]
    dispatch(
        "studium_public_source_open_supplement",
        {"id": source_id, "open_supplement": True, "open_licensed": True},
        session=session,
    )
    excerpt = dispatch(
        "studium_excerpt_record",
        {"source_id": source_id, "url": url, "text": text},
        session=session,
    )
    assert excerpt["status"] == "recorded", excerpt
    return str(excerpt["excerpt"]["id"])


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _project(tmp_path)
    stored = dispatch(
        "studium_blueprint_store",
        {"sections": [{"id": "hidrostatica", "title": "Presión hidrostática"}]},
        session=session,
    )
    assert stored["status"] == "recorded", stored
    dispatch(
        "studium_academic_blueprint_store",
        {
            "profile_key": "ADVANCED_UNDERGRADUATE",
            "subject": "Mecánica de Fluidos",
            "parts": [
                {
                    "id": "part-1",
                    "title": "Fundamentos",
                    "chapters": [
                        {
                            "id": "hidrostatica",
                            "title": "Presión hidrostática",
                            "learning_objectives": ["deducir la ecuación hidrostática"],
                            "sections": [
                                {
                                    "id": "hidrostatica.1",
                                    "title": "Equilibrio",
                                    "concepts": [
                                        {
                                            "id": "presion-estatica",
                                            "title": "Presión estática",
                                            "learning_objectives": ["comprender la presión estática"],
                                            "depth": "ADVANCED_UNDERGRADUATE",
                                            "exercises": 2,
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ],
        },
        session=session,
    )
    excerpts = [
        _open_source(
            session,
            "Apuntes de fluidos",
            "https://open.example/math-a",
            "La presión a 10 m de profundidad vale 97903.8 Pa con densidad 998 kg/m^3.",
        ),
        _open_source(
            session,
            "Fluid mechanics notes",
            "https://open.example/math-b",
            "At 10 m depth the pressure is 97903.8 Pa with density 998 kg/m^3.",
        ),
    ]
    return session, root, excerpts


# --- the structured math model -----------------------------------------------


def test_symbolic_latex_and_unit_latex_are_structured():
    tex = symbolic_latex("rho*V*D/mu")
    assert r"\frac" in tex
    assert validate_latex(tex) == []
    assert "**" not in tex and "$" not in tex

    assert unit_latex("kg/(m^2*s^2)") == r"\mathrm{kg}\,\mathrm{m}^{-2}\,\mathrm{s}^{-2}"
    assert unit_latex("m^2/s") == r"\mathrm{m}^{2}\,\mathrm{s}^{-1}"

    assert symbol_names_of("rho*V*D/mu") == ["rho", "V", "D", "mu"]

    substituted = substitution_latex(
        "rho*V*D/mu",
        {"rho": ("998", "kg/m^3"), "V": ("2", "m/s"), "D": ("0.1", "m"), "mu": ("0.001", "Pa*s")},
    )
    assert "998" in substituted
    assert validate_latex(substituted) == []


def test_validate_latex_rejects_untrusted_fragments():
    assert validate_latex("x**2") == ["a computational power operator survived"]
    assert validate_latex("$x$") == ["a raw math delimiter survived"]
    assert validate_latex(r"\frac{1}{2") == ["unbalanced braces"]
    assert validate_latex("") == ["latex is empty"]

    for hostile in ("__import__('os')", "a.b", "x=1", "rho; V"):
        with pytest.raises(MathError):
            symbolic_latex(hostile)


# --- the depth/length verdict ------------------------------------------------


def test_length_match_reports_a_promise_the_pages_do_not_support():
    profile = PROFILES["ADVANCED_UNDERGRADUATE"]
    scope = estimate_book_scope(
        profile=profile,
        chapters=10,
        concepts=40,
        derivations=10,
        worked_examples=10,
        exercises=80,
    )
    short = assess_length_match(scope=scope, actual_pages=int(scope.floor * 0.4))
    assert short["verdict"] == "UNDER_TARGET"
    assert short["matches"] is False
    assert "declared depth" in short["message"]

    inside = assess_length_match(scope=scope, actual_pages=round(scope.estimate))
    assert inside["verdict"] == "WITHIN_RANGE"
    assert inside["matches"] is True

    empty = assess_length_match(scope=scope, actual_pages=0)
    assert empty["verdict"] == "NO_OUTPUT"


# --- difficulty and problem-type gating --------------------------------------


def test_challenge_difficulty_and_problem_types_are_gated(tmp_path, monkeypatch):
    assert "CHALLENGE" in EXERCISE_DIFFICULTIES
    assert {"MULTI_STEP", "SYMBOLIC", "INTERPRETATION", "APPLICATION"} <= PROBLEM_TYPES

    session, _root, excerpts = _setup(tmp_path, monkeypatch)
    base = {
        "section": "hidrostatica",
        "prompt": "Calcula la presión hidrostática con los datos indicados.",
        "expected": "97903.8",
        "excerpts": excerpts,
        "role": "practice",
    }
    accepted = dispatch(
        "studium_problem_record",
        {**base, "difficulty": "CHALLENGE", "problem_type": "MULTI_STEP"},
        session=session,
    )
    assert accepted["status"] == "recorded", accepted
    assert accepted["problem"]["difficulty"] == "CHALLENGE"
    assert accepted["problem"]["problem_type"] == "MULTI_STEP"

    bad_difficulty = dispatch("studium_problem_record", {**base, "difficulty": "IMPOSSIBLE"}, session=session)
    assert bad_difficulty["status"] == "mcp.invalid_input"

    bad_type = dispatch("studium_problem_record", {**base, "problem_type": "NONSENSE"}, session=session)
    assert bad_type["status"] == "mcp.invalid_input"


# --- structured solutions -----------------------------------------------------


def _structured_solution():
    return {
        "given": [
            {"symbol": "rho", "value": "998", "unit": "kg/m^3", "meaning": "densidad del agua"},
            {"symbol": "g", "value": "9.81", "unit": "m/s^2", "meaning": "aceleración de la gravedad"},
            {"symbol": "h", "value": "10", "unit": "m", "meaning": "profundidad"},
        ],
        "unknown": "presión manométrica p, en pascales",
        "model": [{"name": "Hidrostática", "latex": r"p = \rho\, g\, h", "symbolic": "rho*g*h"}],
        "assumptions": ["fluido en reposo", "densidad uniforme"],
        "steps": [
            {"text": "Se aplica la ecuación fundamental de la hidrostática.", "equation": r"p = \rho\, g\, h"},
            {"text": "Se sustituyen los valores medidos.", "expression": "998*9.81*10", "expected": "97903.8", "unit": "Pa"},
        ],
        "result": r"p = 9.79\times10^{4}\,\mathrm{Pa}",
        "interpretation": "Diez metros de agua añaden casi una atmósfera de presión.",
        "limitations": ["el agua se supone incompresible"],
        "mistakes": ["confundir presión manométrica con presión absoluta"],
    }


def test_structured_solution_records_and_reproduces_every_step(tmp_path, monkeypatch):
    session, _root, excerpts = _setup(tmp_path, monkeypatch)
    recorded = dispatch(
        "studium_problem_record",
        {
            "section": "hidrostatica",
            "prompt": "Calcula la presión a 10 m de profundidad con densidad 998 kg/m^3.",
            "expected": "97903.8",
            "excerpts": excerpts,
            "role": "worked",
            "problem_type": "MULTI_STEP",
            "solution": _structured_solution(),
        },
        session=session,
    )
    assert recorded["status"] == "recorded", recorded
    problem_id = recorded["problem"]["id"]

    checked = dispatch("studium_problem_check", {"id": problem_id}, session=session)
    assert checked["status"] == "two_witnesses"
    # A reproduced step is evidence, not a proof: the overall status stays the
    # same two-witness status and is never upgraded by the step replay.
    assert checked["problem"]["status"] == "two_witnesses"
    assert checked["steps_reproduced"] is True
    assert len(checked["step_checks"]) == 1
    assert checked["step_checks"][0]["reproduced"] is True


def test_a_step_that_does_not_reproduce_is_reported_not_hidden(tmp_path, monkeypatch):
    session, root, excerpts = _setup(tmp_path, monkeypatch)
    solution = _structured_solution()
    solution["steps"][1]["expected"] = "123.0"
    recorded = dispatch(
        "studium_problem_record",
        {
            "section": "hidrostatica",
            "prompt": "Calcula la presión a 10 m de profundidad con densidad 998 kg/m^3.",
            "expected": "97903.8",
            "excerpts": excerpts,
            "role": "worked",
            "solution": solution,
        },
        session=session,
    )
    assert recorded["status"] == "recorded", recorded
    problem_id = recorded["problem"]["id"]

    checked = dispatch("studium_problem_check", {"id": problem_id}, session=session)
    assert checked["steps_reproduced"] is False
    assert checked["step_checks"][0]["reproduced"] is False

    # Fill the book so the renderer emits the worked box, then confirm the
    # failed step is visible instead of being quietly dropped.
    for text in (
        "En un fluido en reposo la presión aumenta con la profundidad de forma lineal.",
        "La medición de la presión se realiza comparando con una referencia conocida.",
    ):
        dispatch("studium_paragraph_record", {"section": "hidrostatica", "text": text, "excerpts": excerpts}, session=session)
    rendered = dispatch("studium_render", {}, session=session)
    assert rendered["status"] == "rendered", rendered
    tex = (root / "latex" / "draft.tex").read_text(encoding="utf-8")
    assert "no reproducido" in tex


def test_structured_solution_is_typeset_and_the_raw_expression_is_not_shown(tmp_path, monkeypatch):
    session, root, excerpts = _setup(tmp_path, monkeypatch)
    dispatch(
        "studium_problem_record",
        {
            "section": "hidrostatica",
            "prompt": "Calcula la presión a 10 m de profundidad con densidad 998 kg/m^3.",
            "expected": "97903.8",
            "excerpts": excerpts,
            "role": "worked",
            "problem_type": "MULTI_STEP",
            "solution": _structured_solution(),
        },
        session=session,
    )
    for text in (
        "En un fluido en reposo la presión aumenta con la profundidad de forma lineal.",
        "La medición de la presión se realiza comparando con una referencia conocida.",
    ):
        dispatch("studium_paragraph_record", {"section": "hidrostatica", "text": text, "excerpts": excerpts}, session=session)

    rendered = dispatch("studium_render", {}, session=session)
    assert rendered["status"] == "rendered", rendered
    tex = (root / "latex" / "draft.tex").read_text(encoding="utf-8")

    # The structured body is typeset with its own labels.
    for label in ("Modelo físico", "Hipótesis", "Desarrollo", "Sustitución numérica", "Resultado", "Errores frecuentes"):
        assert label in tex
    # The substitution uses the measured values and their units.
    assert r"998" in tex and r"\mathrm{kg}" in tex
    # The verifier's raw input expression is never printed as the mathematics.
    assert "998*9.81*10" not in tex
    assert "rho*g*h" not in tex


# --- backwards compatibility --------------------------------------------------


def test_a_problem_without_a_solution_keeps_working(tmp_path, monkeypatch):
    session, _root, excerpts = _setup(tmp_path, monkeypatch)
    recorded = dispatch(
        "studium_problem_record",
        {
            "section": "hidrostatica",
            "prompt": "Determina la presión a 20 m de profundidad con densidad 998 kg/m^3.",
            "expected": "195819.6",
            "excerpts": excerpts,
            "role": "practice",
            "difficulty": "INTERMEDIATE",
        },
        session=session,
    )
    assert recorded["status"] == "recorded", recorded
    assert "solution" not in recorded["problem"]

    checked = dispatch("studium_problem_check", {"id": recorded["problem"]["id"]}, session=session)
    assert checked["status"] == "two_witnesses"
    assert "steps_reproduced" not in checked


def _explode(*_args, **_kwargs):
    raise AssertionError("must not fetch")
