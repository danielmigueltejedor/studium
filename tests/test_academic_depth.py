"""The adaptive academic depth engine.

Planning, derivations, notation, completeness reports, and their LaTeX output.
Every claim here is checked against what the pipeline actually returns.
"""

from studium.authoring.depth.length import (
    LENGTH_PREFERENCES,
    estimate_book_scope,
    length_preference,
    validate_length_target,
)
from studium.authoring.depth.profiles import (
    PROFILE_KEYS,
    PROFILES,
    profile_requirements,
    resolve_depth_profile,
)
from studium.mcp.server import dispatch, handle, open_workspace, tool_names

_COURSE = {
    "course": "Mecánica de Fluidos",
    "university": "Universidad de León",
    "degree": "Grado en Ingeniería Aeroespacial",
    "language": "es",
    "profile": "STEM",
}


def _project(tmp_path, slug="fluidos"):
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


def _excerpts(session):
    return [
        _open_source(
            session,
            "Apuntes de fluidos",
            "https://open.example/fluidos-a",
            "La presión a 4.905 m de profundidad vale 48118.05 Pa con densidad 1000 kg/m^3.",
        ),
        _open_source(
            session,
            "Fluid mechanics notes",
            "https://open.example/fluidos-b",
            "At 4.905 m depth the pressure is 48118.05 Pa with density 1000 kg/m^3.",
        ),
    ]


def _blueprint(session, sections=None):
    stored = dispatch(
        "studium_blueprint_store",
        {"sections": sections or [{"id": "hidrostatica", "title": "Presión hidrostática"}]},
        session=session,
    )
    assert stored["status"] == "recorded", stored
    return stored


def _academic(session, concepts=("presion-estatica",)):
    # The first concept id must not collide with its chapter id.
    chapter_concepts = [
        {
            "id": concept_id,
            "title": concept_id.replace("-", " ").title(),
            "learning_objectives": [f"comprender {concept_id}"],
            "depth": "ADVANCED_UNDERGRADUATE",
            "exercises": 2,
        }
        for concept_id in concepts
    ]
    stored = dispatch(
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
                                    "concepts": chapter_concepts,
                                }
                            ],
                        }
                    ],
                }
            ],
        },
        session=session,
    )
    assert stored["status"] == "recorded", stored
    return stored


# --- depth profiles and length ------------------------------------------------


def test_profiles_resolve_and_are_ordered_by_depth():
    seen = []
    for key in PROFILE_KEYS:
        profile, error = resolve_depth_profile(key)
        assert error is None
        assert profile is not None
        assert profile.key == key
        requirements = profile_requirements(profile)
        assert requirements["profile"] == key
        seen.append(profile.academic_level)
    assert seen == sorted(seen)
    assert len(seen) == len(PROFILES)
    unknown, error = resolve_depth_profile("DOCTORATE")
    assert unknown is None
    assert error is not None
    assert error["status"] == "mcp.invalid_input"


def test_length_is_derived_from_scope_and_bad_targets_are_explained():
    profile = PROFILES["ADVANCED_UNDERGRADUATE"]
    small = estimate_book_scope(
        profile=profile, chapters=1, concepts=2, derivations=1,
        worked_examples=1, exercises=2,
    )
    large = estimate_book_scope(
        profile=profile, chapters=10, concepts=40, derivations=10,
        worked_examples=10, exercises=80,
    )
    assert large.estimate > small.estimate
    assert small.floor < small.estimate < small.ceiling

    below = validate_length_target(scope=small, target_pages=1)
    assert any("below" in note for note in below)
    above = validate_length_target(scope=small, target_pages=10_000)
    assert any("above" in note for note in above)
    fits = validate_length_target(scope=small, target_pages=int(small.estimate))
    assert any("fits" in note for note in fits)

    chosen, error = length_preference("comprehensive")
    assert chosen == "COMPREHENSIVE"
    assert error is None
    assert set(LENGTH_PREFERENCES) >= {"CONCISE", "COMPREHENSIVE", "AUTO"}
    missing, error = length_preference("ENDLESS")
    assert missing is None
    assert error is not None


def test_depth_plan_uses_the_scope_and_stores_the_plan(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, _root = _project(tmp_path)
    _blueprint(session)
    _academic(session)

    planned = dispatch(
        "studium_depth_plan",
        {
            "academic_depth": "ADVANCED_UNDERGRADUATE",
            "length": "COMPREHENSIVE",
            "target_pages": 40,
        },
        session=session,
    )
    assert planned["status"] == "planned", planned
    assert planned["source"] == "academic_blueprint"
    assert planned["academic_depth"]["profile"] == "ADVANCED_UNDERGRADUATE"
    assert planned["length"]["estimate"] > 0
    assert planned["validation"]

    status = dispatch("studium_depth_plan_status", {}, session=session)
    assert status["status"] == "ok"
    assert status["plan"]["length"]["preference"] == "COMPREHENSIVE"

    explicit = dispatch(
        "studium_depth_plan",
        {"academic_depth": "GRADUATE", "curriculum_scope": [{"id": "c1", "title": "Presión", "exercises": 1}]},
        session=session,
    )
    assert explicit["source"] == "curriculum_scope"

    bad = dispatch("studium_depth_plan", {"academic_depth": "MASTER"}, session=session)
    assert bad["status"] == "mcp.invalid_input"


def test_academic_blueprint_round_trips_and_rejects_unknown_concepts(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, _root = _project(tmp_path)
    _blueprint(session)
    _academic(session)

    stored = dispatch("studium_academic_blueprint_get", {}, session=session)
    assert stored["status"] == "ok"
    assert stored["blueprint"]["profile_key"] == "ADVANCED_UNDERGRADUATE"
    assert stored["blueprint"]["parts"][0]["chapters"][0]["id"] == "hidrostatica"

    excerpt = _excerpts(session)[0]
    rejected = dispatch(
        "studium_paragraph_record",
        {
            "section": "hidrostatica",
            "text": "Esta explicación menciona un concepto que no existe en el plan académico almacenado.",
            "excerpts": [excerpt],
            "concepts": ["concepto-inexistente"],
        },
        session=session,
    )
    assert rejected["status"] == "paragraph.concept_unknown"


# --- derivations --------------------------------------------------------------


def _torricelli(session, equation=r"\(V = \sqrt{2gh}\)"):
    recorded = dispatch(
        "studium_derivation_record",
        {
            "section": "hidrostatica",
            "name": "Torricelli",
            "equation": equation,
            "equation_id": "eq-torricelli",
            "assumptions": ["depósito abierto a la atmósfera"],
            "governing_principles": ["conservación de la energía"],
            "steps": ["aplicar Bernoulli", "despejar V"],
            "variables": {"V": "velocidad de salida (m/s)"},
            "limitations": ["no incluye pérdidas viscosas"],
        },
        session=session,
    )
    assert recorded["status"] == "recorded", recorded
    return str(recorded["derivation"]["id"])


def test_derivation_checks_combine_into_independent_verification(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, _root = _project(tmp_path)
    _blueprint(session, [{"id": "hidrostatica", "title": "Presión hidrostática"}])
    derivation_id = _torricelli(session)

    checked = dispatch(
        "studium_derivation_check",
        {
            "id": derivation_id,
            "symbolic": {
                "equation_left": "V^2",
                "equation_right": "2*g*h",
                "solution": {"V": "sqrt(2*g*h)"},
            },
            "numeric": {
                "expression": "sqrt(2*g*h)",
                "values": {"g": 9.81, "h": 4.905},
                "claimed": 9.81,
            },
            "dimensions": {
                "expression": "sqrt(g*h)",
                "symbol_units": {"g": "m/s^2", "h": "m"},
                "expected_unit": "m/s",
            },
        },
        session=session,
    )
    assert checked["status"] == "checked", checked
    assert checked["verification_status"] == "INDEPENDENTLY_VERIFIED"
    methods = {check["method"] for check in checked["derivation"]["verification"]["checks"]}
    assert methods == {"symbolic", "numeric_substitution", "dimensional"}

    listed = dispatch("studium_derivation_list", {}, session=session)
    assert listed["status"] == "ok"
    assert listed["derivations"][0]["id"] == derivation_id


def test_a_failed_derivation_check_is_not_softened(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, _root = _project(tmp_path)
    _blueprint(session)
    derivation_id = _torricelli(session, equation=r"\(V = g h\)")

    checked = dispatch(
        "studium_derivation_check",
        {
            "id": derivation_id,
            "symbolic": {
                "equation_left": "V^2",
                "equation_right": "2*g*h",
                "solution": {"V": "g*h"},
            },
        },
        session=session,
    )
    assert checked["status"] == "checked"
    assert checked["verification_status"] == "FAILED"
    assert checked["derivation"]["verification"]["status"] == "FAILED"


# --- notation and terminology -------------------------------------------------


def test_notation_and_terminology_reject_conflicts(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, _root = _project(tmp_path)
    _blueprint(session)

    first = dispatch(
        "studium_notation_record",
        {"section": "hidrostatica", "symbol": "p", "meaning": "presión estática", "units": "Pa"},
        session=session,
    )
    assert first["status"] == "recorded", first
    assert first["entry"]["id"].startswith("SYM-")

    conflict = dispatch(
        "studium_notation_record",
        {"section": "hidrostatica", "symbol": "p", "meaning": "densidad del fluido", "units": "kg/m^3"},
        session=session,
    )
    assert conflict["status"] == "notation.conflict"

    notation = dispatch("studium_notation_list", {}, session=session)
    assert notation["status"] == "ok"
    assert [row["symbol"] for row in notation["entries"]] == ["p"]

    term = dispatch(
        "studium_terminology_record",
        {"section": "hidrostatica", "term": "manómetro", "definition": "instrumento que mide la presión de un fluido"},
        session=session,
    )
    assert term["status"] == "recorded"
    terminology = dispatch("studium_terminology_list", {}, session=session)
    assert terminology["entries"][0]["term"] == "manómetro"


# --- completeness and consistency reports ------------------------------------


def test_expansion_completeness_and_consistency_reports(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, _root = _project(tmp_path)
    _blueprint(session)
    _academic(session, concepts=("presion-estatica", "manometria"))
    excerpts = _excerpts(session)

    dispatch(
        "studium_paragraph_record",
        {
            "section": "hidrostatica",
            "text": "En un fluido en reposo la presión aumenta con la profundidad de forma lineal. "
            "Este resultado se deduce del equilibrio de una columna elemental de fluido y sirve "
            "para interpretar la medición de presiones.",
            "excerpts": excerpts,
            "concepts": ["presion-estatica"],
        },
        session=session,
    )

    expansion = dispatch("studium_expansion_plan", {"section": "hidrostatica"}, session=session)
    assert expansion["status"] == "ok"
    assert expansion["concepts"]["planned"] == 2
    assert expansion["concepts"]["covered"] == 1
    assert [gap["concept"] for gap in expansion["concept_gaps"]] == ["manometria"]
    assert isinstance(expansion["next_step"], str) and expansion["next_step"]

    completeness = dispatch("studium_section_completeness", {"section": "hidrostatica"}, session=session)
    assert completeness["status"] == "ok"
    assert completeness["summary"]["sections"] == 1
    assert completeness["summary"]["incomplete"] == 1

    coverage = dispatch("studium_source_coverage", {"section": "hidrostatica"}, session=session)
    assert coverage["status"] == "ok"
    assert coverage["totals"]["sources_recorded"] == 2

    consistency = dispatch("studium_consistency_report", {}, session=session)
    assert consistency["status"] == "ok"
    assert consistency["consistent"] is True
    assert consistency["findings"] == 0

    context = dispatch("studium_section_context", {"section": "hidrostatica"}, session=session)
    assert context["status"] == "ok"
    assert context["next_step"]

    unknown = dispatch("studium_expansion_plan", {"section": "no-existe"}, session=session)
    assert unknown["status"] == "expansion.section_unknown"


def test_resume_packet_and_quality_report_are_honest(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, _root = _project(tmp_path)
    _blueprint(session)
    _academic(session)
    excerpts = _excerpts(session)
    dispatch(
        "studium_paragraph_record",
        {
            "section": "hidrostatica",
            "text": "En un fluido en reposo la presión aumenta con la profundidad de forma lineal. "
            "La deducción parte del equilibrio de una columna elemental de fluido.",
            "excerpts": excerpts,
            "concepts": ["presion-estatica"],
        },
        session=session,
    )
    _torricelli(session)

    resume = dispatch("studium_resume_packet", {}, session=session)
    assert resume["status"] == "ok"
    assert resume["depth_plan"]
    assert isinstance(resume["next_steps"], list)

    report = dispatch("studium_quality_report", {}, session=session)
    assert report["status"] == "ok"
    assert report["counts"]["derivations"] == 1
    assert report["derivation_statuses"] == {"UNVERIFIED": 1}
    assert any("ACADEMICALLY_REVIEWED" in item for item in report["limitations"])


# --- professional LaTeX output ------------------------------------------------


def _full_book(session):
    _blueprint(session, [{"id": "hidrostatica", "title": "Presión hidrostática"}])
    _academic(session)
    excerpts = _excerpts(session)
    for text in (
        "En un fluido en reposo la presión aumenta con la profundidad de forma lineal. "
        "Este resultado se deduce del equilibrio de una columna elemental de fluido.",
        "La medición de la presión se realiza con manómetros que comparan la columna "
        "del fluido con una referencia conocida, como la atmósfera.",
    ):
        recorded = dispatch(
            "studium_paragraph_record",
            {"section": "hidrostatica", "text": text, "excerpts": excerpts},
            session=session,
        )
        assert recorded["status"] == "recorded", recorded

    dispatch(
        "studium_notation_record",
        {"section": "hidrostatica", "symbol": "p", "meaning": "presión estática", "units": "Pa"},
        session=session,
    )
    dispatch(
        "studium_terminology_record",
        {"section": "hidrostatica", "term": "manómetro", "definition": "instrumento que mide la presión"},
        session=session,
    )
    _torricelli(session)

    from studium.authoring.computation import evaluate

    expression = "1000*9.81*4.905"
    expected = f"{float(evaluate(expression)):.12g}"
    checked = dispatch(
        "studium_computation_check",
        {"expression": expression, "result": expected, "section": "hidrostatica"},
        session=session,
    )
    assert checked["status"] == "replayed" and checked["correct"] is True

    worked = dispatch(
        "studium_problem_record",
        {
            "section": "hidrostatica",
            "prompt": "Calcula la presión a 4.905 m de profundidad con densidad 1000 kg/m^3.",
            "expected": expected,
            "excerpts": excerpts,
            "role": "worked",
        },
        session=session,
    )
    assert worked["status"] == "recorded", worked
    practice = dispatch(
        "studium_problem_record",
        {
            "section": "hidrostatica",
            "prompt": "Determina la presión a 9.81 m de profundidad con la misma densidad.",
            "expected": "96236.1",
            "excerpts": excerpts,
            "role": "practice",
            "difficulty": "INTERMEDIATE",
            "learning_objectives": ["presion-estatica"],
        },
        session=session,
    )
    assert practice["status"] == "recorded", practice
    return excerpts


def test_render_fills_the_notation_sheet_exercises_and_derivations(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _project(tmp_path)
    _full_book(session)
    rendered = dispatch("studium_render", {}, session=session)
    assert rendered["status"] == "rendered", rendered
    tex = (root / "latex" / "draft.tex").read_text(encoding="utf-8")

    assert r"\usepackage[hidelinks]{hyperref}" in tex
    assert r"\usepackage[hyphens]{url}" in tex
    assert r"\url{https://open.example/fluidos-a}" in tex
    assert "Símbolo" in tex and "presión estática" in tex
    assert "Ejercicios" in tex and "INTERMEDIATE" in tex
    assert "Derivaciones" in tex and "Torricelli" in tex
    assert "Notation" not in tex
    assert "PAR-" not in tex
    assert r"\begin{tcolorbox}" in tex


def test_new_tools_are_registered_with_annotations():
    names = set(tool_names())
    expected = {
        "studium_academic_blueprint_store",
        "studium_academic_blueprint_get",
        "studium_depth_plan",
        "studium_depth_plan_status",
        "studium_derivation_record",
        "studium_derivation_check",
        "studium_derivation_list",
        "studium_notation_record",
        "studium_notation_list",
        "studium_terminology_record",
        "studium_terminology_list",
        "studium_expansion_plan",
        "studium_section_completeness",
        "studium_source_coverage",
        "studium_consistency_report",
        "studium_section_context",
        "studium_resume_packet",
        "studium_quality_report",
    }
    assert expected <= names
    listed = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    advertised = {tool["name"]: tool for tool in listed["result"]["tools"]}
    for tool_name in expected:
        assert advertised[tool_name]["annotations"]["class"] in {"READ", "WRITE", "COMPUTE"}


def _explode(*_args, **_kwargs):
    raise AssertionError("must not fetch")
