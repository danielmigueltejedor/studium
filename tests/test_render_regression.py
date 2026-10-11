"""Regression tests for the LaTeX renderer.

Covers: escape functions, formula rendering, bibliography, notation tables,
worked problems, derivation boxes, exercise boxes, and full document structure.
These tests must pass before and after type-safety fixes to render.py.
"""


import pytest

from studium.authoring.render import (
    emit_prose,
    latex_escape,
    render_draft,
    render_text_run,
)
from studium.mcp.server import dispatch, open_workspace


def _explode(*_args, **_kwargs):
    raise RuntimeError("network access not allowed in tests")


# ---------------------------------------------------------------------------
# Unit: latex_escape
# ---------------------------------------------------------------------------


def test_latex_escape_special_characters():
    assert latex_escape("10% & $5") == r"10\% \& \$5"
    assert latex_escape("{x}") == r"\{x\}"
    assert latex_escape("a_b^c") == r"a\_b\textasciicircum{}c"
    assert latex_escape("") == ""


def test_latex_escape_backslash():
    assert latex_escape("a\\b") == r"a\textbackslash{}b"


# ---------------------------------------------------------------------------
# Unit: render_text_run — inline formulas and plain prose
# ---------------------------------------------------------------------------


def test_render_text_run_plain_prose():
    result = render_text_run("hello world")
    assert result == "hello world"


def test_render_text_run_inline_math():
    result = render_text_run(r"The value \(x^2\) is positive.")
    assert r"\(x^2\)" in result
    assert "The value" in result


def test_render_text_run_dollar_math():
    result = render_text_run("Force is $F = ma$ always.")
    assert r"\(" in result or "$" in result
    assert "Force is" in result


def test_render_text_run_escapes_special():
    result = render_text_run("100% done & ready")
    assert r"\%" in result
    assert r"\&" in result


# ---------------------------------------------------------------------------
# Unit: emit_prose — paragraphs, display math, code blocks
# ---------------------------------------------------------------------------


def test_emit_prose_single_paragraph():
    lines = emit_prose("A single paragraph of text.")
    assert len(lines) == 1
    assert "single paragraph" in lines[0]


def test_emit_prose_two_paragraphs():
    lines = emit_prose("First paragraph.\n\nSecond paragraph.")
    assert len(lines) == 2


def test_emit_prose_display_math():
    lines = emit_prose(r"Before. \[ E = mc^2 \] After.")
    joined = "\n".join(lines)
    assert r"\[" in joined


def test_emit_prose_code_block():
    text = "Before.\n\n```python\nprint('hi')\n```\n\nAfter."
    lines = emit_prose(text)
    joined = "\n".join(lines)
    assert "print" in joined


def test_emit_prose_italic():
    lines = emit_prose("Italic text here.", italic=True)
    assert any(r"\textit{" in line for line in lines)


# ---------------------------------------------------------------------------
# Integration helpers
# ---------------------------------------------------------------------------


def _project(tmp_path, profile="STEM"):
    session = open_workspace(str(tmp_path))
    created = dispatch(
        "studium_project_create",
        {
            "slug": "testbook",
            "course": "Test Course",
            "university": "Test University",
            "degree": "Test Degree",
            "language": "es",
            "profile": profile,
        },
        session=session,
    )
    assert created["status"] == "created", created
    return session, tmp_path / "testbook"


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
        _open_source(session, "Source A", "https://open.example/a", "Pressure increases with depth linearly in a fluid at rest."),
        _open_source(session, "Source B", "https://open.example/b", "The hydrostatic equation: p = rho * g * h."),
    ]


def _full_setup(tmp_path, monkeypatch):
    """Build a minimal complete book with paragraphs, notation, derivation, problems."""
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _project(tmp_path)
    dispatch(
        "studium_blueprint_store",
        {"sections": [{"id": "presion", "title": "Presión hidrostática"}]},
        session=session,
    )
    dispatch(
        "studium_academic_blueprint_store",
        {
            "profile_key": "ADVANCED_UNDERGRADUATE",
            "subject": "Test",
            "parts": [
                {
                    "id": "part-1",
                    "title": "Part One",
                    "chapters": [
                        {
                            "id": "presion",
                            "title": "Presión hidrostática",
                            "learning_objectives": ["learn pressure"],
                            "sections": [
                                {
                                    "id": "presion.1",
                                    "title": "Basics",
                                    "concepts": [
                                        {
                                            "id": "pressure",
                                            "title": "Pressure",
                                            "learning_objectives": ["understand pressure"],
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
    excerpts = _excerpts(session)
    for text in (
        "En un fluido en reposo la presión aumenta linealmente con la profundidad.",
        "La medición de la presión se realiza con manómetros que comparan columnas.",
    ):
        dispatch(
            "studium_paragraph_record",
            {"section": "presion", "text": text, "excerpts": excerpts},
            session=session,
        )
    dispatch(
        "studium_notation_record",
        {"section": "presion", "symbol": "p", "meaning": "presión estática", "units": "Pa"},
        session=session,
    )
    dispatch(
        "studium_derivation_record",
        {
            "section": "presion",
            "name": "Ecuación hidrostática",
            "equation": r"\(p = \rho g h\)",
            "steps": ["Start from dp/dz = -rho*g", "Integrate"],
            "variables": {"p": {"meaning": "pressure", "units": "Pa"}, "rho": {"meaning": "density", "units": "kg/m^3"}},
        },
        session=session,
    )

    from studium.authoring.computation import evaluate

    expression = "1000*9.81*4.905"
    expected = f"{float(evaluate(expression)):.12g}"
    dispatch(
        "studium_computation_check",
        {"expression": expression, "result": expected, "section": "presion"},
        session=session,
    )
    dispatch(
        "studium_problem_record",
        {
            "section": "presion",
            "prompt": "Calcula la presión a 4.905 m.",
            "expected": expected,
            "excerpts": excerpts,
            "role": "worked",
        },
        session=session,
    )
    dispatch(
        "studium_problem_record",
        {
            "section": "presion",
            "prompt": "Determina la presión a 9.81 m.",
            "expected": "96236.1",
            "excerpts": excerpts,
            "role": "practice",
            "difficulty": "INTERMEDIATE",
            "learning_objectives": ["pressure"],
        },
        session=session,
    )
    return session, root


# ---------------------------------------------------------------------------
# Integration: full document structure
# ---------------------------------------------------------------------------


class TestDocumentStructure:
    """The rendered LaTeX must contain all expected structural elements."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        self.session, self.root = _full_setup(tmp_path, monkeypatch)
        rendered = render_draft(self.root)
        assert rendered["status"] in ("rendered", "compiler_missing", "incomplete"), rendered
        self.tex = (self.root / "latex" / "draft.tex").read_text(encoding="utf-8")

    def test_document_begins_and_ends(self):
        assert r"\begin{document}" in self.tex
        assert r"\end{document}" in self.tex

    def test_chapter_present(self):
        assert r"\chapter{Presión hidrostática}" in self.tex

    def test_table_of_contents(self):
        assert r"\tableofcontents" in self.tex

    def test_frontmatter_and_backmatter(self):
        assert r"\frontmatter" in self.tex
        assert r"\backmatter" in self.tex

    def test_appendix_present(self):
        assert r"\appendix" in self.tex

    def test_chapter_label(self):
        assert r"\label{chap:presion}" in self.tex


# ---------------------------------------------------------------------------
# Integration: formulas in LaTeX output
# ---------------------------------------------------------------------------


class TestFormulaRendering:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        self.session, self.root = _full_setup(tmp_path, monkeypatch)
        render_draft(self.root)
        self.tex = (self.root / "latex" / "draft.tex").read_text(encoding="utf-8")

    def test_derivation_equation_rendered(self):
        assert "rho" in self.tex or r"\rho" in self.tex

    def test_display_math_present(self):
        assert r"\[" in self.tex or r"\begin{equation" in self.tex

    def test_derivation_box_present(self):
        assert r"\begin{tcolorbox}" in self.tex


# ---------------------------------------------------------------------------
# Integration: notation table
# ---------------------------------------------------------------------------


class TestNotationTable:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        self.session, self.root = _full_setup(tmp_path, monkeypatch)
        render_draft(self.root)
        self.tex = (self.root / "latex" / "draft.tex").read_text(encoding="utf-8")

    def test_notation_table_has_symbol(self):
        assert "presión estática" in self.tex

    def test_notation_table_has_units(self):
        assert "Pa" in self.tex

    def test_notation_uses_tabular(self):
        assert r"\begin{tabular}" in self.tex


# ---------------------------------------------------------------------------
# Integration: bibliography
# ---------------------------------------------------------------------------


class TestBibliography:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        self.session, self.root = _full_setup(tmp_path, monkeypatch)
        render_draft(self.root)
        self.tex = (self.root / "latex" / "draft.tex").read_text(encoding="utf-8")

    def test_bibliography_environment(self):
        assert r"\begin{thebibliography}" in self.tex
        assert r"\end{thebibliography}" in self.tex

    def test_bibitem_present(self):
        assert r"\bibitem{" in self.tex

    def test_source_url_rendered(self):
        assert r"\url{https://open.example/" in self.tex


# ---------------------------------------------------------------------------
# Integration: exercises and worked problems
# ---------------------------------------------------------------------------


class TestExercisesAndProblems:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        self.session, self.root = _full_setup(tmp_path, monkeypatch)
        render_draft(self.root)
        self.tex = (self.root / "latex" / "draft.tex").read_text(encoding="utf-8")

    def test_exercise_box_present(self):
        assert "Ejercicios" in self.tex or "Exercises" in self.tex

    def test_exercise_difficulty_shown(self):
        assert "INTERMEDIATE" in self.tex

    def test_worked_problem_box(self):
        assert "4.905" in self.tex


# ---------------------------------------------------------------------------
# Integration: references (no PAR- ids leak into output)
# ---------------------------------------------------------------------------


class TestReferences:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        self.session, self.root = _full_setup(tmp_path, monkeypatch)
        render_draft(self.root)
        self.tex = (self.root / "latex" / "draft.tex").read_text(encoding="utf-8")

    def test_no_paragraph_ids_leak(self):
        assert "PAR-" not in self.tex

    def test_hyperref_loaded(self):
        assert r"\usepackage[hidelinks]{hyperref}" in self.tex

    def test_url_package_loaded(self):
        assert r"\usepackage[hyphens]{url}" in self.tex


# ---------------------------------------------------------------------------
# Integration: notation table units in math mode
# ---------------------------------------------------------------------------


class TestNotationUnits:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        self.session, self.root = _full_setup(tmp_path, monkeypatch)
        render_draft(self.root)
        self.tex = (self.root / "latex" / "draft.tex").read_text(encoding="utf-8")

    def test_units_in_math_mode(self):
        assert r"$\mathrm{Pa}$" in self.tex

    def test_units_not_plain_escaped(self):
        in_tabular = False
        for line in self.tex.split("\n"):
            if r"\begin{tabular}" in line:
                in_tabular = True
            if r"\end{tabular}" in line:
                in_tabular = False
            if not in_tabular:
                continue
            if r"\textbf" in line or r"\hline" in line:
                continue
            if " Pa " in line or line.strip().endswith("Pa \\\\"):
                assert r"\mathrm{Pa}" in line, f"Plain 'Pa' in notation row: {line.strip()}"


# ---------------------------------------------------------------------------
# Integration: source audit grouping
# ---------------------------------------------------------------------------


class TestAuditGrouping:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        self.session, self.root = _full_setup(tmp_path, monkeypatch)
        render_draft(self.root)
        self.tex = (self.root / "latex" / "draft.tex").read_text(encoding="utf-8")

    def test_audit_has_paragraph_markers(self):
        assert r"\P1:" in self.tex or "\\P1" in self.tex or "¶1:" in self.tex

    def test_audit_groups_sources(self):
        source_a_count = self.tex.count("Source A")
        assert source_a_count >= 1


# ---------------------------------------------------------------------------
# Integration: study plan with academic blueprint
# ---------------------------------------------------------------------------


class TestStudyPlan:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        self.session, self.root = _full_setup(tmp_path, monkeypatch)
        render_draft(self.root)
        self.tex = (self.root / "latex" / "draft.tex").read_text(encoding="utf-8")

    def test_study_plan_shows_chapter(self):
        assert r"\checkmark" in self.tex or r"$\square$" in self.tex

    def test_study_plan_shows_learning_objectives(self):
        assert "learn pressure" in self.tex or "itemize" in self.tex

    def test_study_plan_shows_concept_count(self):
        assert "concepts planned" in self.tex or "1 concepts planned" in self.tex

    def test_amssymb_loaded(self):
        assert r"\usepackage{amssymb}" in self.tex


# ---------------------------------------------------------------------------
# Integration: LaTeX cross-reference labels
# ---------------------------------------------------------------------------


class TestCrossReferenceLabels:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        monkeypatch.setattr("urllib.request.urlopen", _explode)
        session, root = _project(tmp_path)
        dispatch(
            "studium_blueprint_store",
            {"sections": [{"id": "thermo", "title": "Thermodynamics"}]},
            session=session,
        )
        excerpts = _excerpts(session)
        for text in (
            "Heat flows from hot to cold bodies.",
            "Energy is conserved in isolated systems.",
        ):
            dispatch(
                "studium_paragraph_record",
                {"section": "thermo", "text": text, "excerpts": excerpts},
                session=session,
            )
        dispatch(
            "studium_derivation_record",
            {
                "section": "thermo",
                "name": "Ideal gas law",
                "equation": r"\(PV = nRT\)",
                "equation_id": "eq-ideal-gas",
                "steps": ["Start from kinetic theory"],
                "variables": {"P": {"meaning": "pressure", "units": "Pa"}},
            },
            session=session,
        )
        render_draft(root)
        self.tex = (root / "latex" / "draft.tex").read_text(encoding="utf-8")

    def test_chapter_label_present(self):
        assert r"\label{chap:thermo}" in self.tex

    def test_equation_label_present(self):
        assert r"\label{eq:eq-ideal-gas}" in self.tex
