"""History, literature and life-science books render without engineering leftovers."""

import re
import shutil
import subprocess

import pytest
from test_render_regression import _excerpts, _explode, _project

from studium.authoring.languages import describe, messages
from studium.authoring.render import _collapse_runs, _inline_code, _solution_body, _url_tex, render_draft
from studium.domain.profiles import depth_thresholds, infer_topic_profile, resolve_topic_profile
from studium.mcp.server import dispatch, open_workspace


@pytest.mark.parametrize(
    "topic, expected",
    [
        ("Biología celular y molecular", "LIFE_SCIENCES"),
        ("Genética de poblaciones", "LIFE_SCIENCES"),
        ("Medicina interna", "LIFE_SCIENCES"),
        ("Cell biology", "LIFE_SCIENCES"),
        ("Neurociencia cognitiva", "LIFE_SCIENCES"),
        ("Algoritmos genéticos", "COMPUTER_SCIENCE"),
        ("Ingeniería biomédica", "STEM"),
        ("Historia de España", None),
        ("Literatura española", None),
    ],
)
def test_life_science_topics_are_not_stored_as_general(topic, expected):
    assert infer_topic_profile(topic) == expected
    assert resolve_topic_profile(topic, None) == (expected or "GENERAL")


def test_a_requested_profile_survives_for_topics_without_a_detected_field():
    assert resolve_topic_profile("Historia de España", "HUMANITIES") == "HUMANITIES"
    assert resolve_topic_profile("Biología celular", "HUMANITIES") == "LIFE_SCIENCES"


def test_topic_book_creation_stores_the_life_science_profile(tmp_path):
    session = open_workspace(str(tmp_path))
    created = dispatch("studium_project_create", {"slug": "bio", "topic": "Biología celular"}, session=session)
    assert created["status"] == "created", created
    assert 'domain_profile = "LIFE_SCIENCES"' in (tmp_path / "bio" / "project.toml").read_text(encoding="utf-8")


def test_life_science_depth_matches_a_narrative_book_not_an_engineering_course():
    life = depth_thresholds("LIFE_SCIENCES")
    assert (life.min_sections, life.min_sources) == (6, 10)
    assert life.min_explanation_words == 450
    assert depth_thresholds("STEM").min_sections == 8


def test_life_science_chapters_need_no_derivation_figure_or_notation(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _project(tmp_path, profile="LIFE_SCIENCES")
    dispatch("studium_blueprint_store", {"sections": [{"id": "celula", "title": "La célula"}]}, session=session)
    dispatch(
        "studium_paragraph_record",
        {"section": "celula", "text": "La célula es la unidad básica de los seres vivos.", "excerpts": _excerpts(session)},
        session=session,
    )
    report = dispatch("studium_section_completeness", {"section_id": "celula"}, session=session)
    checks = {item["id"]: item for item in report["sections"][0]["checks"]}
    for identifier in ("derivation", "derivations_checked", "exercise_difficulties", "figures_checked", "notation"):
        assert checks[identifier]["applies"] is False, identifier
    assert checks["sources"]["applies"] is True


def test_inline_code_keeps_shift_operators_and_dashes_literal():
    tex = _inline_code("a >> b << c -- d")
    assert ">>" not in tex and "<<" not in tex and "--" not in tex
    assert tex.count(r"\textgreater{}") == 2
    assert tex.count(r"\textless{}") == 2


@pytest.mark.skipif(not (shutil.which("pdflatex") and shutil.which("pdftotext")), reason="needs pdflatex and pdftotext")
def test_inline_code_prints_literally_under_spanish_babel(tmp_path):
    source = "\n".join(
        [
            r"\documentclass{article}",
            r"\usepackage[T1]{fontenc}",
            r"\usepackage[utf8]{inputenc}",
            r"\usepackage{lmodern}",
            r"\usepackage[spanish]{babel}",
            r"\begin{document}",
            "Operadores " + _inline_code("a >> b << c") + " y opciones " + _inline_code("cmd --flag -- fin") + " al final.",
            r"\end{document}",
        ]
    )
    (tmp_path / "t.tex").write_text(source, encoding="utf-8")
    subprocess.run(["pdflatex", "-interaction=nonstopmode", "t.tex"], cwd=tmp_path, check=True, capture_output=True)
    text = subprocess.run(["pdftotext", "t.pdf", "-"], cwd=tmp_path, check=True, capture_output=True, text=True).stdout
    flat = re.sub(r"\s+", " ", text)
    assert "a >> b << c" in flat
    assert "cmd --flag -- fin" in flat
    assert "»" not in flat and "«" not in flat and "–" not in flat


def test_bibliography_url_encodes_accented_titles():
    assert _url_tex("https://es.wikipedia.org/wiki/Mester_de_clerecía") == r"\url{https://es.wikipedia.org/wiki/Mester_de_clerec%C3%ADa}"
    assert _url_tex("https://es.wikipedia.org/wiki/Luis_de_Góngora") == r"\url{https://es.wikipedia.org/wiki/Luis_de_G%C3%B3ngora}"


def test_bibliography_url_leaves_ascii_and_encoded_addresses_unchanged():
    plain = "https://example.org/a/b_c-d.html?x=1&y=2#frag"
    assert _url_tex(plain) == r"\url{" + plain + "}"
    encoded = "https://es.wikipedia.org/wiki/Reyes_Cat%C3%B3licos"
    assert _url_tex(encoded) == r"\url{" + encoded + "}"


def test_collapse_runs_prints_a_long_run_once_and_short_runs_in_full():
    long_run = [(f"¶{n}", "dos testimonios.") for n in range(1, 82)]
    assert _collapse_runs(long_run) == ["¶1–¶81: dos testimonios."]
    mixed = [("¶1", "a."), ("¶2", "a."), ("¶3", "b."), ("¶4", "b."), ("¶5", "b."), ("¶6", "b."), ("¶7", "a.")]
    assert _collapse_runs(mixed) == ["¶1: a.", "¶2: a.", "¶3–¶6: b.", "¶7: a."]
    assert _collapse_runs([]) == []


def _history_book(tmp_path, monkeypatch, profile):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _project(tmp_path, profile=profile)
    dispatch("studium_blueprint_store", {"sections": [{"id": "reyes", "title": "Los Reyes Católicos"}]}, session=session)
    dispatch(
        "studium_paragraph_record",
        {"section": "reyes", "text": "La unión dinástica de Castilla y Aragón no creó un estado único.", "excerpts": _excerpts(session)},
        session=session,
    )
    return session, root


@pytest.mark.parametrize("profile", ["HUMANITIES", "LIFE_SCIENCES"])
def test_narrative_books_omit_appendices_that_have_no_material(tmp_path, monkeypatch, profile):
    _session, root = _history_book(tmp_path, monkeypatch, profile)
    render_draft(root)
    tex = (root / "latex" / "draft.tex").read_text(encoding="utf-8")
    assert r"\chapter{Los Reyes Católicos}" in tex
    for title in ("Notación", "Hoja de fórmulas", "Plan de estudio"):
        assert r"\chapter{" + title + "}" not in tex
    assert r"\chapter{Auditoría de fuentes}" in tex


def test_a_general_book_keeps_its_empty_appendices_as_visible_gaps(tmp_path, monkeypatch):
    _session, root = _history_book(tmp_path, monkeypatch, "GENERAL")
    render_draft(root)
    tex = (root / "latex" / "draft.tex").read_text(encoding="utf-8")
    assert r"\chapter{Notación}" in tex
    assert r"\chapter{Hoja de fórmulas}" in tex


def test_a_narrative_book_that_selects_its_appendices_keeps_them(tmp_path, monkeypatch):
    _session, root = _history_book(tmp_path, monkeypatch, "HUMANITIES")
    project = root / "project.toml"
    project.write_text(project.read_text(encoding="utf-8") + '\n[render]\nappendices = ["notation", "audit"]\n', encoding="utf-8")
    render_draft(root)
    tex = (root / "latex" / "draft.tex").read_text(encoding="utf-8")
    assert r"\chapter{Notación}" in tex
    assert r"\chapter{Hoja de fórmulas}" not in tex


_SOLUTION = {
    "given": [{"symbol": "a", "value": 1605, "unit": "dimensionless", "meaning": "año"}],
    "model": [{"name": "Intervalo", "latex": r"\Delta = b - a"}],
    "steps": [{"text": "Restar.", "equation": r"\Delta = 1615 - 1605", "expression": "1615-1605", "expected": 10}],
}


def test_a_history_worked_problem_does_not_announce_a_physical_model(tmp_path):
    from test_render_regression import _project as project

    _session, root = project(tmp_path, profile="HUMANITIES")
    language = describe("es")
    rendered = "\n".join(_solution_body({"id": "PRB-0001"}, _SOLUTION, messages(language), language, root=root))
    assert r"\textbf{Modelo}" in rendered
    assert "Modelo físico" not in rendered


def test_an_engineering_worked_problem_keeps_the_physical_model_label(tmp_path):
    from test_render_regression import _project as project

    _session, root = project(tmp_path, profile="STEM")
    language = describe("es")
    rendered = "\n".join(_solution_body({"id": "PRB-0001"}, _SOLUTION, messages(language), language, root=root))
    assert "Modelo físico" in rendered
