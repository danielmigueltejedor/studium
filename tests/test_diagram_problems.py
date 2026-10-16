"""Diagrams as first-class parts of problems: recorded through MCP, checked, placed and kept current."""

import json

import pytest

from studium.authoring.render import find_engine, render_draft
from studium.mcp.server import dispatch, open_workspace, tool_names

ULE = "ule-teoria-estructuras"
_HAS_TEX = find_engine() is not None


def _explode(*_args, **_kwargs):
    raise AssertionError("must not fetch")


def _beam_spec(point=12):
    return {
        "length": 6,
        "points": {"A": 0, "C": 2, "B": 6},
        "supports": [{"at": "A", "type": "pin"}, {"at": "B", "type": "roller"}],
        "loads": [{"type": "point", "at": "C", "value": point, "direction": "down"}],
        "convention": ULE,
        "units": {"force": "kN", "length": "m"},
    }


def _solution():
    return {
        "given": [{"symbol": "P", "value": 12, "unit": "kN", "meaning": "carga puntual"}],
        "unknown": "reacciones y flector máximo",
        "steps": [{"text": "Reacción en A", "expression": "12*4/6", "expected": "8", "unit": "kN"}],
        "result": "R_A = 8\\ \\mathrm{kN}",
        "interpretation": "El flector máximo está bajo la carga.",
        "mistakes": ["olvidar el salto del cortante bajo la carga"],
    }


def _open_source(session, title, url, text):
    record = dispatch("studium_public_source_record", {"title": title, "url": url, "text": text}, session=session)
    source_id = record["candidate"]["id"]
    dispatch(
        "studium_public_source_open_supplement",
        {"id": source_id, "open_supplement": True, "open_licensed": True},
        session=session,
    )
    excerpt = dispatch("studium_excerpt_record", {"source_id": source_id, "url": url, "text": text}, session=session)
    return str(excerpt["excerpt"]["id"])


@pytest.fixture
def book(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session = open_workspace(str(tmp_path))
    created = dispatch(
        "studium_project_create",
        {"slug": "vigas", "course": "Estructuras", "university": "U", "degree": "G", "language": "es", "profile": "STEM"},
        session=session,
    )
    assert created["status"] == "created"
    dispatch("studium_blueprint_store", {"sections": [{"id": "vigas", "title": "Vigas"}]}, session=session)
    excerpts = [
        _open_source(session, "Fuente A", "https://open.example/a", "A beam carries loads perpendicular to its axis."),
        _open_source(session, "Fuente B", "https://open.example/b", "The shear force jumps by the value of a point load."),
    ]
    dispatch(
        "studium_paragraph_record",
        {"section": "vigas", "text": "Una viga soporta cargas perpendiculares a su eje.", "excerpts": excerpts},
        session=session,
    )
    return session, tmp_path / "vigas", excerpts


def _problem(session, excerpts, *, role="worked", structure=None, prompt="Calcule las reacciones y dibuje los diagramas."):
    recorded = dispatch(
        "studium_problem_record",
        {
            "section": "vigas",
            "prompt": prompt,
            "expected": "8",
            "excerpts": excerpts,
            "role": role,
            "solution": _solution(),
            "structure": structure if structure is not None else {"family": "beam", "spec": _beam_spec()},
        },
        session=session,
    )
    assert recorded["status"] == "recorded", recorded
    return recorded["problem"]["id"]


def test_new_tools_are_listed():
    names = tool_names()
    for name in (
        "studium_diagram_catalogue",
        "studium_structure_solve",
        "studium_diagram_preview",
        "studium_diagram_record",
        "studium_diagram_verify",
        "studium_diagram_regenerate",
        "studium_diagram_inspect",
        "studium_diagram_report",
        "studium_problem_structure_update",
    ):
        assert name in names


def test_catalogue_and_solve(book):
    session, _, _ = book
    catalogue = dispatch("studium_diagram_catalogue", {}, session=session)
    assert "beam.internal_forces" in catalogue["generators"]
    assert ULE in catalogue["conventions"]
    assert "free_body" in catalogue["stages"]
    solved = dispatch("studium_structure_solve", {"family": "beam", "spec": _beam_spec()}, session=session)
    assert solved["status"] == "solved"
    assert solved["data"]["reactions"]["R_A"]["exact"] == "8"
    assert solved["verification"]["status"] == "mathematically_verified"
    unknown = dispatch("studium_structure_solve", {"family": "planet", "spec": {"a": 1}}, session=session)
    assert unknown["status"] == "diagram.family_unknown"


def test_preview_returns_tikz_and_evidence_without_storing(book):
    session, root, _ = book
    preview = dispatch(
        "studium_diagram_preview", {"generator": "beam.internal_forces", "spec": _beam_spec()}, session=session
    )
    assert preview["stored"] is False
    assert "% studium:series M" in preview["tikz"]
    assert preview["verification"]["flags"]["representation_matches_data"] is True
    assert not (root / "figures" / "figures.jsonl").exists() or "beam" not in (root / "figures" / "figures.jsonl").read_text()


def test_inconsistent_claims_are_rejected_and_not_stored(book):
    session, _, excerpts = book
    rejected = dispatch(
        "studium_diagram_record",
        {
            "generator": "beam.internal_forces",
            "caption": "Diagramas.",
            "section": "vigas",
            "excerpts": excerpts,
            "spec": _beam_spec(),
            "claims": {"reactions": {"R_A": "6"}},
        },
        session=session,
    )
    assert rejected["status"] == "rejected"
    assert rejected["stored"] is False
    assert "claimed reaction R_A" in rejected["verification"]["failed"]
    listing = dispatch("studium_figure_list", {}, session=session)
    assert listing["count"] == 0


def test_problem_with_contradicted_structure_is_rejected(book):
    session, _, excerpts = book
    result = dispatch(
        "studium_problem_record",
        {
            "section": "vigas",
            "prompt": "Calcule las reacciones.",
            "expected": "8",
            "excerpts": excerpts,
            "structure": {"family": "beam", "spec": _beam_spec(), "claims": {"reactions": {"R_B": "8"}}},
        },
        session=session,
    )
    assert result["status"] == "problem.structure_contradicted"


@pytest.mark.skipif(not _HAS_TEX, reason="pdflatex not installed")
def test_problem_diagrams_render_inside_the_worked_solution(book):
    session, root, excerpts = book
    problem_id = _problem(session, excerpts)
    for generator, stage, key in (
        ("beam.statement", "statement", "viga-enunciado"),
        ("beam.free_body", "free_body", "viga-dsl"),
        ("beam.internal_forces", "graphical", "viga-esfuerzos"),
    ):
        recorded = dispatch(
            "studium_diagram_record",
            {"generator": generator, "caption": f"Figura {key}.", "problem": problem_id, "stage": stage, "key": key},
            session=session,
        )
        assert recorded["status"] == "recorded", recorded
        assert recorded["compiled"] is True
        assert recorded["verification"]["status"] == "mathematically_verified"
    render_draft(root)
    tex = (root / "latex" / "draft.tex").read_text(encoding="utf-8")
    worked = tex[tex.index("Problema resuelto") :]
    statement = worked.index(r"\label{fig:viga-enunciado}")
    free_body = worked.index(r"\label{fig:viga-dsl}")
    laws = worked.index(r"\begin{cases}")
    graphical = worked.index(r"\label{fig:viga-esfuerzos}")
    assert statement < free_body < laws < graphical
    assert "Diagrama de sólido libre" in worked and "Solución gráfica" in worked
    assert "Comprobaciones automáticas" in worked
    assert "Verificación de los diagramas" in tex
    report = dispatch("studium_diagram_report", {}, session=session)
    assert report["counts"] == {"mathematically_verified": 3}


@pytest.mark.skipif(not _HAS_TEX, reason="pdflatex not installed")
def test_editing_the_loads_makes_diagrams_stale_until_regenerated(book):
    session, root, excerpts = book
    problem_id = _problem(session, excerpts)
    recorded = dispatch(
        "studium_diagram_record",
        {"generator": "beam.internal_forces", "caption": "Diagramas.", "problem": problem_id, "stage": "graphical", "key": "esf"},
        session=session,
    )
    figure_id = recorded["figure_id"]
    old_source = _figure(root, figure_id)["source"]
    updated = dispatch(
        "studium_problem_structure_update",
        {"id": problem_id, "structure": {"family": "beam", "spec": _beam_spec(point=18)}, "regenerate": False},
        session=session,
    )
    assert updated["status"] == "updated"
    assert updated["problem"]["status"] == "stale" or updated["problem"]["status"] == "unchecked"
    stale = dispatch("studium_diagram_verify", {"id": figure_id}, session=session)
    assert stale["status"] == "stale"
    render_draft(root)
    assert r"\label{fig:esf}" not in (root / "latex" / "draft.tex").read_text(encoding="utf-8")
    regenerated = dispatch("studium_diagram_regenerate", {"problem": problem_id}, session=session)
    assert regenerated["diagrams"][0]["status"] == "mathematically_verified"
    assert regenerated["diagrams"][0]["compiled"] is True
    new_source = _figure(root, figure_id)["source"]
    assert new_source != old_source
    assert dispatch("studium_diagram_verify", {"id": figure_id}, session=session)["verification"]["status"] == "mathematically_verified"
    render_draft(root)
    assert r"\label{fig:esf}" in (root / "latex" / "draft.tex").read_text(encoding="utf-8")


@pytest.mark.skipif(not _HAS_TEX, reason="pdflatex not installed")
def test_visual_inspection_is_an_attestation_not_a_proof(book):
    session, root, excerpts = book
    recorded = dispatch(
        "studium_diagram_record",
        {"generator": "beam.statement", "caption": "Viga.", "section": "vigas", "excerpts": excerpts, "spec": _beam_spec(), "key": "v"},
        session=session,
    )
    figure_id = recorded["figure_id"]
    passed = dispatch("studium_diagram_inspect", {"id": figure_id, "passed": True, "inspector": "agent"}, session=session)
    assert passed["verification"]["flags"]["visually_inspected"] is True
    assert passed["verification"]["status"] == "mathematically_verified"
    failed = dispatch(
        "studium_diagram_inspect", {"id": figure_id, "passed": False, "notes": "labels overlap"}, session=session
    )
    assert failed["verification"]["status"] == "verification_failed"
    render_draft(root)
    assert r"\label{fig:v}" not in (root / "latex" / "draft.tex").read_text(encoding="utf-8")


def test_every_worked_problem_is_rendered_in_its_chapter(book):
    """Regression: only the first worked problem of a chapter used to appear in the chapter."""

    session, root, excerpts = book
    _problem(session, excerpts, prompt="Primer problema resuelto de la viga.")
    _problem(session, excerpts, structure={"family": "beam", "spec": _beam_spec(point=6)}, prompt="Segundo problema resuelto de la viga.")
    render_draft(root)
    tex = (root / "latex" / "draft.tex").read_text(encoding="utf-8")
    body = tex[: tex.index(r"\appendix")]
    assert "Primer problema resuelto" in body and "Segundo problema resuelto" in body
    assert "Problema resuelto 2" in body


def test_problem_inputs_include_the_structure(book):
    session, _, excerpts = book
    problem_id = _problem(session, excerpts)
    checked = dispatch("studium_problem_check", {"id": problem_id}, session=session)
    assert checked["structure_check"]["status"] == "mathematically_verified"
    dispatch(
        "studium_problem_structure_update",
        {"id": problem_id, "structure": {"family": "beam", "spec": _beam_spec(point=18)}},
        session=session,
    )
    listed = dispatch("studium_problem_list", {}, session=session)
    problem = next(item for item in listed["problems"] if item["id"] == problem_id)
    assert problem["status"] in ("stale", "unchecked")
    assert problem["correct"] is False


def _figure(root, figure_id):
    records = [json.loads(line) for line in (root / "figures" / "figures.jsonl").read_text().splitlines() if line.strip()]
    return [record for record in records if record.get("id") == figure_id][-1]


@pytest.mark.skipif(not _HAS_TEX, reason="pdflatex not installed")
def test_figures_follow_the_paragraph_that_cites_them(book):
    """Regression: every figure of a chapter used to be dumped after its first paragraph, in recording order."""

    session, root, excerpts = book
    for key in ("primera", "segunda"):
        recorded = dispatch(
            "studium_figure_record",
            {"section": "vigas", "caption": f"Figura {key}.", "kind": "tikz", "source": r"\draw (0,0) -- (1,1);", "excerpts": excerpts, "key": key},
            session=session,
        )
        dispatch("studium_figure_check", {"id": recorded["figure"]["id"]}, session=session)
    dispatch(
        "studium_paragraph_record",
        {"section": "vigas", "text": "Un párrafo intermedio sin figuras sobre vigas y cargas.", "excerpts": excerpts},
        session=session,
    )
    dispatch(
        "studium_paragraph_record",
        {"section": "vigas", "text": "La {{fig:segunda}} muestra una viga y la {{fig:primera}} otra viga.", "excerpts": excerpts},
        session=session,
    )
    render_draft(root)
    tex = (root / "latex" / "draft.tex").read_text(encoding="utf-8")
    citing = tex.index("muestra una viga")
    middle = tex.index("Un párrafo intermedio")
    second, first = tex.index(r"\label{fig:segunda}"), tex.index(r"\label{fig:primera}")
    assert middle < citing < second < first


def test_result_generator_cannot_be_relabelled_as_statement(book):
    session, root, excerpts = book
    problem_id = _problem(session, excerpts)
    before = (root / 'figures' / 'figures.jsonl').read_bytes() if (root / 'figures' / 'figures.jsonl').exists() else b''
    result = dispatch('studium_diagram_record', {'generator': 'beam.internal_forces', 'caption': 'Results',
        'problem': problem_id, 'stage': 'statement'}, session=session)
    assert result['status'] == 'diagram.unsafe_statement'
    assert result['stored'] is False
    after = (root / 'figures' / 'figures.jsonl').read_bytes() if (root / 'figures' / 'figures.jsonl').exists() else b''
    assert before == after


def test_result_bearing_generators_do_not_advertise_statement_safety():
    from studium.diagrams.registry import generator

    for name in ('beam.internal_forces', 'beam.free_body', 'section.properties', 'thin_wall.geometry', 'stress_state.element'):
        assert 'statement' not in generator(name).stages
    assert 'statement' in generator('beam.statement').stages


def test_legacy_statement_results_move_to_solution_without_record_mutation(book):
    from copy import deepcopy

    from studium.authoring.diagrams import problem_figures, statement_placement_issue
    from studium.storage.records import FIGURES, append_jsonl

    _, root, _ = book
    record = {'id': 'FIG-legacy', 'section': 'vigas', 'source': 'preserved drawing',
              'diagram': {'generator': 'beam.internal_forces', 'problem': 'PRB-legacy', 'stage': 'statement'}}
    original = deepcopy(record)
    append_jsonl(root / FIGURES, record)
    before = (root / FIGURES).read_bytes()
    assert statement_placement_issue(record)
    placed = problem_figures(root, 'PRB-legacy')[0]
    assert placed['diagram']['stage'] == 'solution'
    assert placed['source'] == original['source']
    assert record == original and (root / FIGURES).read_bytes() == before
