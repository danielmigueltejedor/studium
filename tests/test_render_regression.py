"""Regression tests for the LaTeX renderer.

Covers: escape functions, formula rendering, bibliography, notation tables,
worked problems, derivation boxes, exercise boxes, and full document structure.
These tests must pass before and after type-safety fixes to render.py.
"""


import pytest

from studium.authoring.render import (
    _display_math,
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


def test_render_text_run_spanish_decimal_dollar_math():
    # A digit-leading explicit span with braces is math, not currency:
    # "$0{,}01$" must become \(0{,}01\), never \$0\{,\}01\$.
    result = render_text_run("por debajo de $0{,}01$ del total")
    assert r"\(0{,}01\)" in result
    assert "\\$" not in result


@pytest.mark.parametrize("number", ["1.08", "5", "0,25"])
def test_numeric_dollar_math_does_not_steal_the_next_formula_delimiter(number):
    text = f"El factor es ${number}$ y $F=ma$."
    result = render_text_run(text)
    assert rf"\({number}\)" in result
    assert r"\(F=ma\)" in result
    assert r"\$" not in result


def test_unpaired_prices_and_comma_separated_prices_remain_literal():
    assert render_text_run("Cuesta $5.") == r"Cuesta \$5."
    assert render_text_run("Precios: $5, $10.") == r"Precios: \$5, \$10."
    assert render_text_run("Precios: $5 $10.") == r"Precios: \$5 \$10."


def test_render_text_run_escapes_special():
    result = render_text_run("100% done & ready")
    assert r"\%" in result
    assert r"\&" in result


def test_render_text_run_groups_consecutive_unicode_superscripts():
    # A run of Unicode superscripts must become one group: "s⁻¹" -> ^{ -1 },
    # never "^{-}^{1}", which LaTeX rejects as a double superscript.
    result = render_text_run("gradiente de 100 s⁻¹ constante")
    assert "^{-1}" in result
    assert "^{-}^{" not in result


def test_display_math_translates_unicode_formula():
    """Regression: a stored result in Unicode becomes LaTeX math.

    ``_display_math`` wraps stored solution strings in display math but used to
    emit them raw, so a result like ``F = 1,8·10⁻³ N`` failed to compile. It must
    translate Unicode operators and group consecutive superscripts.
    """

    rendered = "\n".join(_display_math("F = 1,8·10⁻³ N"))
    assert r"\cdot" in rendered
    assert "10^{-3}" in rendered
    assert "⁻" not in rendered
    assert "^{-}^{" not in rendered


def test_display_math_keeps_bare_latex():
    """Regression: a stored equation in bare LaTeX is passed through unchanged.

    Bare LaTeX must not be routed through the Unicode translator, which would
    turn ``\\frac`` into ``\\backslash frac``.
    """

    rendered = "\n".join(_display_math(r"Re = \frac{\rho V L}{\mu}"))
    assert r"\frac{\rho V L}{\mu}" in rendered
    assert r"\backslash" not in rendered


def test_render_text_run_ascii_subscript_with_unicode_superscript():
    # "V_entrada²" mixes an ASCII subscript with a Unicode superscript and must
    # stay inside a single formula: V_{entrada}^{2}, not "V_)" + "^{2}".
    result = render_text_run("como ρ(V_entrada² - V_salida²)/2")
    assert "_{entrada}" in result
    assert "V_{entrada}^{2}" in result


# ---------------------------------------------------------------------------
# Unit: emit_prose — paragraphs, display math, code blocks
# ---------------------------------------------------------------------------


def test_emit_prose_single_paragraph():
    lines = emit_prose("A single paragraph of text.")
    assert len([line for line in lines if line]) == 1
    assert "single paragraph" in lines[0]


def test_emit_prose_two_paragraphs():
    lines = emit_prose("First paragraph.\n\nSecond paragraph.")
    assert len([line for line in lines if line]) == 2
    assert "First paragraph.\n\nSecond paragraph." in "\n".join(lines)


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

    def test_status_line_does_not_shrink_the_rest_of_the_box(self):
        """The footnote-size status line of a derivation is grouped, so the next derivation keeps its size."""

        assert r"\noindent\footnotesize" not in self.tex.replace(r"{\noindent\footnotesize", "")

    def test_formula_sheet_typesets_bare_latex(self):
        """Regression: a bare-LaTeX equation is display math, not escaped prose.

        The formula sheet previously passed the stored equation through
        ``emit_prose``, which turned ``\\frac`` into ``\\textbackslash{}frac``
        and broke the LaTeX build. The chapter derivation box already used
        ``_display_math``; the formula sheet must agree with it.
        """

        dispatch(
            "studium_derivation_record",
            {
                "section": "presion",
                "name": "Número de Reynolds",
                "equation": r"Re = \frac{\rho V L}{\mu}",
            },
            session=self.session,
        )
        render_draft(self.root)
        tex = (self.root / "latex" / "draft.tex").read_text(encoding="utf-8")
        assert r"\frac{\rho V L}{\mu}" in tex
        assert r"\textbackslash{}frac" not in tex


class TestDerivationRemove:
    def test_remove_derivation_hides_it_everywhere(self, tmp_path, monkeypatch):
        session, root = _full_setup(tmp_path, monkeypatch)
        recorded = dispatch(
            "studium_derivation_record",
            {"section": "presion", "name": "Borrable", "equation": r"e = m c^2"},
            session=session,
        )
        derivation_id = recorded["derivation"]["id"]
        state_before = (root / ".studium" / "state.json").read_bytes()
        paragraphs_before = (root / "draft" / "paragraphs.jsonl").read_bytes()
        removed = dispatch("studium_derivation_remove", {"id": derivation_id}, session=session)
        assert removed["status"] == "removed"
        assert removed["derivation_id"] == derivation_id
        assert removed["released"] is False
        assert (root / ".studium" / "state.json").read_bytes() == state_before
        assert (root / "draft" / "paragraphs.jsonl").read_bytes() == paragraphs_before
        listed = dispatch("studium_derivation_list", {}, session=session)
        assert all(item["id"] != derivation_id for item in listed["derivations"])
        missing = dispatch("studium_derivation_remove", {"id": "DER-9999"}, session=session)
        assert missing["status"] == "derivation.not_found"
        blank = dispatch("studium_derivation_remove", {}, session=session)
        assert blank["status"] == "mcp.invalid_input"


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

    def test_notation_uses_a_breakable_longtable(self):
        appendix = self.tex[self.tex.index("presión estática") - 2000 :]
        assert r"\begin{longtable}" in appendix


# ---------------------------------------------------------------------------
# Regression: notation table subscript symbols
# ---------------------------------------------------------------------------


class TestNotationSubscriptSymbols:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        self.session, self.root = _full_setup(tmp_path, monkeypatch)
        dispatch(
            "studium_notation_record",
            {"section": "presion", "symbol": "F_B", "meaning": "fuerza de empuje", "units": "N"},
            session=self.session,
        )
        dispatch(
            "studium_notation_record",
            {"section": "presion", "symbol": "ρ", "meaning": "densidad del fluido", "units": "kg/m³"},
            session=self.session,
        )
        render_draft(self.root)
        self.tex = (self.root / "latex" / "draft.tex").read_text(encoding="utf-8")

    def test_subscript_symbol_in_math_mode(self):
        assert r"$F_{B}$" in self.tex

    def test_subscript_not_escaped(self):
        assert r"F\_B" not in self.tex

    def test_greek_symbol_in_math_mode(self):
        assert r"$\rho$" in self.tex

    def test_greek_symbol_not_text_wrapped(self):
        assert r"\mathrm{\(\rho\)}" not in self.tex


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
        assert "Intermedio" in self.tex

    def test_worked_problem_box(self):
        assert "4.905" in self.tex


# ---------------------------------------------------------------------------
# Integration: the solutions appendix is a manual, not a list of raw floats
# ---------------------------------------------------------------------------


def _solutions_setup(tmp_path, monkeypatch):
    """A worked problem and a practice problem that carry a stored solution."""

    from studium.authoring.excerpts import excerpts_by_id

    session, root = _full_setup(tmp_path, monkeypatch)
    excerpts = list(excerpts_by_id(root))[:2]
    dispatch(
        "studium_problem_record",
        {
            "section": "presion",
            "prompt": "Explica el método y calcula la presión a 4.905 m.",
            "expected": "48118.05",
            "excerpts": excerpts,
            "role": "practice",
            "difficulty": "INTERMEDIATE",
            "learning_objectives": ["pressure"],
            "solution": {
                "given": [{"symbol": "h", "value": "4.905", "unit": "m", "meaning": "profundidad"}],
                "unknown": "presión manométrica en el fondo",
                "model": [{"name": "Hidrostática", "latex": r"p = \rho g h"}],
                "assumptions": ["el fluido está en reposo"],
                "steps": [{"text": "Se aplica la ecuación fundamental.", "equation": r"p = \rho g h"}],
                "result": r"p = 4{,}81\times10^{4}\ \mathrm{Pa}",
                "interpretation": "La presión crece de forma lineal con la profundidad.",
            },
        },
        session=session,
    )
    dispatch(
        "studium_problem_record",
        {
            "section": "presion",
            "prompt": "Caso resuelto cuya respuesta está tipografiada.",
            "expected": "5.0",
            "excerpts": excerpts,
            "role": "worked",
            "solution": {
                "given": [{"symbol": "p", "value": "5.0", "unit": "Pa", "meaning": "presión"}],
                "unknown": "comprobación del resultado",
                "model": [{"name": "Modelo de prueba", "latex": r"p = 5"}],
                "steps": [{"text": "Se lee el resultado.", "equation": r"p = 5"}],
                "result": r"p = 5{,}0\ \mathrm{Pa}",
            },
        },
        session=session,
    )
    return session, root


class TestSolutionsAppendix:
    """A practice problem with a stored solution renders the full solution."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        self.session, self.root = _solutions_setup(tmp_path, monkeypatch)
        render_draft(self.root)
        self.tex = (self.root / "latex" / "draft.tex").read_text(encoding="utf-8")

    def test_practice_solution_rendered(self):
        # The structured solution body, not just the prompt of the exercise.
        assert r"\noindent\textbf{Datos}" in self.tex
        assert r"\noindent\textbf{Modelo físico}" in self.tex

    def test_practice_solution_result_is_typeset(self):
        # The author's typeset result reaches the appendix.
        assert r"4{,}81\times10^{4}" in self.tex

    def test_worked_appendix_answer_is_typeset(self):
        # A worked problem with a structured solution prints its typeset result
        # instead of a raw machine value.
        assert r"5{,}0\ \mathrm{Pa}" in self.tex

    def test_problem_without_solution_keeps_bare_answer(self):
        # Backwards compatibility: a problem with no structured solution still
        # prints its replayed expected value.
        assert "96236.1" in self.tex


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


# ---------------------------------------------------------------------------
# Integration: hierarchical rendering with academic blueprint
# ---------------------------------------------------------------------------


def test_figure_lines_skips_figures_already_shown(monkeypatch, tmp_path):
    # A chapter with academic sections calls _chapter_lines once per section,
    # but its figures are stored per chapter. The shared ``shown`` set must stop
    # the same drawing from being emitted again for every section.
    from studium.authoring import render as render_mod

    record = {
        "id": "FIG-1",
        "section": "ch1",
        "kind": "tikz",
        "source": r"\draw (0,0) -- (1,1);",
        "caption": "A line.",
    }
    monkeypatch.setattr(render_mod, "figures_in_section", lambda root, section_id: [record])
    monkeypatch.setattr(render_mod, "_checked_output", lambda root, item: tmp_path / "figure.pdf")

    shown: set[str] = set()
    first = render_mod._figure_lines(tmp_path, "ch1", {}, shown)
    second = render_mod._figure_lines(tmp_path, "ch1", {}, shown)

    assert first, "the first call must emit the figure"
    assert second == [], "a figure already shown must not be emitted again"
    assert shown == {"FIG-1"}


class TestHierarchicalRendering:
    """When an academic blueprint exists, the renderer uses its Part/Chapter/Section structure."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        self.session, self.root = _full_setup(tmp_path, monkeypatch)
        rendered = render_draft(self.root)
        assert rendered["status"] in ("rendered", "compiler_missing", "incomplete"), rendered
        self.tex = (self.root / "latex" / "draft.tex").read_text(encoding="utf-8")

    def test_part_from_academic_blueprint(self):
        assert r"\part{Part One}" in self.tex

    def test_chapter_from_academic_blueprint(self):
        assert r"\chapter{Presión hidrostática}" in self.tex

    def test_section_from_academic_blueprint(self):
        assert r"\section{Basics}" in self.tex

    def test_no_duplicate_book_part(self):
        parts = [line for line in self.tex.split("\n") if r"\part{" in line]
        book_name_parts = [p for p in parts if "Part One" not in p]
        assert not book_name_parts, f"Extra \\part outside academic blueprint: {book_name_parts}"


class TestHierarchicalSubsectionPlacement:
    """Paragraphs with a subsection field are placed under the right \\section{}."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        monkeypatch.setattr("urllib.request.urlopen", _explode)
        self.session, self.root = _project(tmp_path)
        dispatch(
            "studium_blueprint_store",
            {"sections": [{"id": "ch1", "title": "Chapter One"}]},
            session=self.session,
        )
        dispatch(
            "studium_academic_blueprint_store",
            {
                "profile_key": "ADVANCED_UNDERGRADUATE",
                "subject": "Test",
                "parts": [
                    {
                        "id": "part-a",
                        "title": "Part A",
                        "chapters": [
                            {
                                "id": "ch1",
                                "title": "Chapter One",
                                "learning_objectives": ["learn ch1"],
                                "sections": [
                                    {
                                        "id": "ch1.intro",
                                        "title": "Introduction",
                                        "concepts": [
                                            {
                                                "id": "c1",
                                                "title": "Concept One",
                                                "learning_objectives": ["lo1"],
                                                "depth": "ADVANCED_UNDERGRADUATE",
                                                "exercises": 1,
                                            }
                                        ],
                                    },
                                    {
                                        "id": "ch1.theory",
                                        "title": "Theory",
                                        "concepts": [
                                            {
                                                "id": "c2",
                                                "title": "Concept Two",
                                                "learning_objectives": ["lo2"],
                                                "depth": "ADVANCED_UNDERGRADUATE",
                                                "exercises": 1,
                                            }
                                        ],
                                    },
                                ],
                            }
                        ],
                    }
                ],
            },
            session=self.session,
        )
        excerpts = _excerpts(self.session)
        dispatch(
            "studium_paragraph_record",
            {"section": "ch1", "text": "This is the chapter introduction.", "excerpts": excerpts},
            session=self.session,
        )
        dispatch(
            "studium_paragraph_record",
            {
                "section": "ch1",
                "subsection": "ch1.intro",
                "text": "This paragraph belongs to the Introduction section.",
                "excerpts": excerpts,
            },
            session=self.session,
        )
        dispatch(
            "studium_paragraph_record",
            {
                "section": "ch1",
                "subsection": "ch1.theory",
                "text": "This paragraph belongs to the Theory section.",
                "excerpts": excerpts,
            },
            session=self.session,
        )
        rendered = render_draft(self.root)
        assert rendered["status"] in ("rendered", "compiler_missing", "incomplete"), rendered
        self.tex = (self.root / "latex" / "draft.tex").read_text(encoding="utf-8")

    def test_chapter_present(self):
        assert r"\chapter{Chapter One}" in self.tex

    def test_section_introduction(self):
        assert r"\section{Introduction}" in self.tex

    def test_section_theory(self):
        assert r"\section{Theory}" in self.tex

    def test_intro_paragraph_in_chapter_body(self):
        chapter_pos = self.tex.index(r"\chapter{Chapter One}")
        intro_section_pos = self.tex.index(r"\section{Introduction}")
        intro_text_pos = self.tex.index("chapter introduction")
        assert chapter_pos < intro_text_pos < intro_section_pos

    def test_section_paragraph_after_section_heading(self):
        intro_section_pos = self.tex.index(r"\section{Introduction}")
        intro_text_pos = self.tex.index("Introduction section")
        assert intro_section_pos < intro_text_pos

    def test_theory_paragraph_after_theory_heading(self):
        theory_section_pos = self.tex.index(r"\section{Theory}")
        theory_text_pos = self.tex.index("Theory section")
        assert theory_section_pos < theory_text_pos

    def test_sections_ordered_correctly(self):
        intro_pos = self.tex.index(r"\section{Introduction}")
        theory_pos = self.tex.index(r"\section{Theory}")
        assert intro_pos < theory_pos


class TestFlatBlueprintFallback:
    """Without an academic blueprint, the old flat rendering still works."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        monkeypatch.setattr("urllib.request.urlopen", _explode)
        self.session, self.root = _project(tmp_path)
        dispatch(
            "studium_blueprint_store",
            {"sections": [{"id": "sec1", "title": "Flat Section"}]},
            session=self.session,
        )
        excerpts = _excerpts(self.session)
        dispatch(
            "studium_paragraph_record",
            {"section": "sec1", "text": "Content of flat section.", "excerpts": excerpts},
            session=self.session,
        )
        rendered = render_draft(self.root)
        assert rendered["status"] in ("rendered", "compiler_missing", "incomplete"), rendered
        self.tex = (self.root / "latex" / "draft.tex").read_text(encoding="utf-8")

    def test_chapter_from_flat_blueprint(self):
        assert r"\chapter{Flat Section}" in self.tex

    def test_no_academic_section_headings(self):
        mainmatter_pos = self.tex.index(r"\mainmatter")
        appendix_pos = self.tex.index(r"\appendix")
        main_body = self.tex[mainmatter_pos:appendix_pos]
        section_count = main_body.count(r"\section{")
        assert section_count == 0


class TestSubsectionRouting:
    """Paragraphs targeting a blueprint subsection render under \\subsection{}."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        monkeypatch.setattr("urllib.request.urlopen", _explode)
        self.session, self.root = _project(tmp_path)
        dispatch(
            "studium_blueprint_store",
            {"sections": [{"id": "ch1", "title": "Chapter One"}]},
            session=self.session,
        )
        dispatch(
            "studium_academic_blueprint_store",
            {
                "profile_key": "ADVANCED_UNDERGRADUATE",
                "subject": "Test",
                "parts": [
                    {
                        "id": "p1",
                        "title": "Part One",
                        "chapters": [
                            {
                                "id": "ch1",
                                "title": "Chapter One",
                                "learning_objectives": ["lo"],
                                "sections": [
                                    {
                                        "id": "ch1.sec1",
                                        "title": "Sec One",
                                        "subsections": [
                                            {
                                                "id": "ch1.sec1.sub1",
                                                "title": "Sub Alpha",
                                                "concepts": [
                                                    {
                                                        "id": "c1",
                                                        "title": "C1",
                                                        "learning_objectives": ["lo1"],
                                                        "depth": "ADVANCED_UNDERGRADUATE",
                                                        "exercises": 1,
                                                    }
                                                ],
                                            }
                                        ],
                                        "concepts": [
                                            {
                                                "id": "c2",
                                                "title": "C2",
                                                "learning_objectives": ["lo2"],
                                                "depth": "ADVANCED_UNDERGRADUATE",
                                                "exercises": 1,
                                            }
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
            session=self.session,
        )
        excerpts = _excerpts(self.session)
        dispatch(
            "studium_paragraph_record",
            {
                "section": "ch1",
                "subsection": "ch1.sec1",
                "text": "Section-level content.",
                "excerpts": excerpts,
            },
            session=self.session,
        )
        dispatch(
            "studium_paragraph_record",
            {
                "section": "ch1",
                "subsection": "ch1.sec1.sub1",
                "text": "Subsection-level content.",
                "excerpts": excerpts,
            },
            session=self.session,
        )
        rendered = render_draft(self.root)
        assert rendered["status"] in ("rendered", "compiler_missing", "incomplete"), rendered
        self.tex = (self.root / "latex" / "draft.tex").read_text(encoding="utf-8")

    def test_section_heading(self):
        assert r"\section{Sec One}" in self.tex

    def test_subsection_heading(self):
        assert r"\subsection{Sub Alpha}" in self.tex

    def test_subsection_content_under_subsection(self):
        subsec_pos = self.tex.index(r"\subsection{Sub Alpha}")
        content_pos = self.tex.index("Subsection-level content")
        assert subsec_pos < content_pos

    def test_section_content_before_subsection(self):
        sec_pos = self.tex.index(r"\section{Sec One}")
        sec_content_pos = self.tex.index("Section-level content")
        subsec_pos = self.tex.index(r"\subsection{Sub Alpha}")
        assert sec_pos < sec_content_pos < subsec_pos


class TestChapterBackMatterOnce:
    """A chapter's derivation and problems render once, at the chapter's end.

    The records are keyed by chapter, but a chapter with several academic
    sections calls the renderer once per section. Before the fix the derivation,
    the worked problem and the practice set repeated after every section and the
    equation label was multiply defined.
    """

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        monkeypatch.setattr("urllib.request.urlopen", _explode)
        self.session, self.root = _project(tmp_path)
        dispatch(
            "studium_blueprint_store",
            {"sections": [{"id": "ch1", "title": "Chapter One"}]},
            session=self.session,
        )
        dispatch(
            "studium_academic_blueprint_store",
            {
                "profile_key": "ADVANCED_UNDERGRADUATE",
                "subject": "Test",
                "parts": [
                    {
                        "id": "p1",
                        "title": "Part One",
                        "chapters": [
                            {
                                "id": "ch1",
                                "title": "Chapter One",
                                "learning_objectives": ["lo"],
                                "sections": [
                                    {
                                        "id": "ch1.sec1",
                                        "title": "Sec One",
                                        "concepts": [
                                            {
                                                "id": "c1",
                                                "title": "C1",
                                                "learning_objectives": ["lo1"],
                                                "depth": "ADVANCED_UNDERGRADUATE",
                                                "exercises": 1,
                                            }
                                        ],
                                    },
                                    {
                                        "id": "ch1.sec2",
                                        "title": "Sec Two",
                                        "concepts": [
                                            {
                                                "id": "c2",
                                                "title": "C2",
                                                "learning_objectives": ["lo2"],
                                                "depth": "ADVANCED_UNDERGRADUATE",
                                                "exercises": 1,
                                            }
                                        ],
                                    },
                                ],
                            }
                        ],
                    }
                ],
            },
            session=self.session,
        )
        excerpts = _excerpts(self.session)
        for subsection in ("ch1.sec1", "ch1.sec2"):
            dispatch(
                "studium_paragraph_record",
                {
                    "section": "ch1",
                    "subsection": subsection,
                    "text": f"Explicación almacenada para {subsection} con suficiente longitud.",
                    "excerpts": excerpts,
                },
                session=self.session,
            )
        dispatch(
            "studium_derivation_record",
            {
                "section": "ch1",
                "name": "Ecuación de prueba",
                "equation": r"\(p = \rho g h\)",
                "equation_id": "eq-prueba",
                "steps": ["Point of departure", "Integrate"],
                "variables": {"p": {"meaning": "presión", "units": "Pa"}},
            },
            session=self.session,
        )
        from studium.authoring.computation import evaluate

        expression = "2*3*4"
        expected = f"{float(evaluate(expression)):.12g}"
        dispatch(
            "studium_computation_check",
            {"expression": expression, "result": expected, "section": "ch1"},
            session=self.session,
        )
        dispatch(
            "studium_problem_record",
            {
                "section": "ch1",
                "prompt": "Calcula el caso resuelto.",
                "expected": expected,
                "excerpts": excerpts,
                "role": "worked",
            },
            session=self.session,
        )
        dispatch(
            "studium_problem_record",
            {
                "section": "ch1",
                "prompt": "Resuelve el caso de práctica.",
                "expected": expected,
                "excerpts": excerpts,
                "role": "practice",
                "difficulty": "INTERMEDIATE",
                "learning_objectives": ["c1"],
            },
            session=self.session,
        )
        rendered = render_draft(self.root)
        assert rendered["status"] in ("rendered", "compiler_missing", "incomplete"), rendered
        self.tex = (self.root / "latex" / "draft.tex").read_text(encoding="utf-8")

    def test_two_academic_sections_present(self):
        assert r"\section{Sec One}" in self.tex
        assert r"\section{Sec Two}" in self.tex

    def test_derivation_box_appears_once(self):
        assert self.tex.count("title={Derivaciones}") == 1

    def test_equation_label_is_not_multiply_defined(self):
        assert self.tex.count(r"\label{eq:eq-prueba}") == 1

    def test_worked_and_practice_appear_once(self):
        main = self.tex[: self.tex.index(r"\appendix")] if r"\appendix" in self.tex else self.tex
        assert main.count("Calcula el caso resuelto.") == 1
        assert main.count("Resuelve el caso de práctica.") == 1

    def test_back_matter_comes_after_the_last_section(self):
        sec_two = self.tex.index(r"\section{Sec Two}")
        derivation = self.tex.index("title={Derivaciones}")
        assert sec_two < derivation


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
        assert "1 concepto planificado." in self.tex or "conceptos planificados." in self.tex
        assert "concepts planned" not in self.tex

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


# ---------------------------------------------------------------------------
# Unit: symbol and unit TeX helpers
# ---------------------------------------------------------------------------


class TestSymbolAndUnitTex:
    def test_greek_symbol_renders_math(self):
        from studium.authoring.render import _symbol_tex

        assert _symbol_tex("ρ") == r"\rho"
        assert _symbol_tex("η") == r"\eta"

    def test_ascii_symbol_through_sympy(self):
        from studium.authoring.render import _symbol_tex

        assert _symbol_tex("p") == "p"
        assert _symbol_tex("p_0") == "p_{0}"
        assert _symbol_tex("F_B") == "F_{B}"

    def test_subscript_braces_preserved(self):
        from studium.authoring.render import _symbol_tex

        result = _symbol_tex("V_{desp}")
        assert "desp" in result
        assert r"\{" not in result

    def test_unit_unicode_superscript(self):
        from studium.authoring.render import _unit_tex

        result = _unit_tex("kg/m³")
        assert r"\(" not in result
        assert "mathrm" in result

    def test_unit_unicode_squared(self):
        from studium.authoring.render import _unit_tex

        result = _unit_tex("m/s²")
        assert r"\(" not in result
        assert "mathrm" in result

    def test_unit_ascii_exponent(self):
        from studium.authoring.render import _unit_tex

        result = _unit_tex("kg/m^3")
        assert "mathrm" in result
        assert r"\(" not in result

    def test_multi_char_greek_latin_spacing(self):
        from studium.authoring.render import _symbol_tex

        result = _symbol_tex("Δp")
        assert result == r"\Delta p"
        assert r"\Deltap" not in result

    def test_greek_greek_spacing(self):
        from studium.authoring.render import _symbol_tex

        result = _symbol_tex("ρg")
        assert result == r"\rho g"


# ---------------------------------------------------------------------------
# Integration: derivation steps with math content
# ---------------------------------------------------------------------------


class TestDerivationStepMath:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        monkeypatch.setattr("urllib.request.urlopen", _explode)
        session, root = _project(tmp_path)
        dispatch(
            "studium_blueprint_store",
            {"sections": [{"id": "hydrostat", "title": "Hydrostatics"}]},
            session=session,
        )
        excerpts = _excerpts(session)
        for text in (
            "Pressure increases linearly with depth.",
            "The hydrostatic equation relates pressure to depth.",
        ):
            dispatch(
                "studium_paragraph_record",
                {"section": "hydrostat", "text": text, "excerpts": excerpts},
                session=session,
            )
        dispatch(
            "studium_derivation_record",
            {
                "section": "hydrostat",
                "name": "Hydrostatic equation",
                "equation": r"\(p = p_0 + \rho g h\)",
                "equation_id": "eq-hydro",
                "steps": [
                    r"Start from \(dp/dz = -\rho g\)",
                    r"Integrate: \(p - p_0 = -\rho g (z - z_0)\)",
                    r"Define depth \(h = -(z - z_0)\)",
                    r"Result: \(p = p_0 + \rho g h\)",
                ],
                "variables": {
                    "ρ": {"meaning": "fluid density", "units": "kg/m³"},
                    "p": {"meaning": "pressure at depth h", "units": "Pa"},
                    "g": {"meaning": "gravitational acceleration", "units": "m/s²"},
                },
            },
            session=session,
        )
        render_draft(root)
        self.tex = (root / "latex" / "draft.tex").read_text(encoding="utf-8")

    def test_explicit_math_in_steps_preserved(self):
        assert r"\(p = p_0 + \rho g h\)" in self.tex or r"p = p_0 + \rho g h" in self.tex

    def test_greek_symbol_in_variables_valid(self):
        assert r"$\rho$" in self.tex
        assert r"\mathrm{\(\rho\)}" not in self.tex

    def test_unicode_unit_renders_cleanly(self):
        assert r"\mathrm{\(^{3}\)}" not in self.tex
        assert r"\mathrm{\(^{2}\)}" not in self.tex

    def test_equation_label_present(self):
        assert r"\label{eq:eq-hydro}" in self.tex


# ---------------------------------------------------------------------------
# Unit: figure numbering and in-text references
# ---------------------------------------------------------------------------


def test_figure_caption_prefix_numbers_and_labels():
    from studium.authoring.render import _figure_caption_prefix

    prefix = _figure_caption_prefix({"id": "FIG-3", "key": "flujo"}, {"figure_ref": "figura"})
    assert r"\refstepcounter{studiumfigure}" in prefix
    assert r"\label{fig:flujo}" in prefix
    assert r"Figura~\thestudiumfigure." in prefix


def test_figure_caption_prefix_falls_back_to_the_id():
    from studium.authoring.render import _figure_caption_prefix

    prefix = _figure_caption_prefix({"id": "FIG-3"}, {"figure_ref": "figura"})
    assert r"\label{fig:fig-3}" in prefix


def test_figure_caption_prefix_speaks_the_book_language():
    from studium.authoring.render import _figure_caption_prefix

    prefix = _figure_caption_prefix({"id": "FIG-1", "key": "x"}, {"figure_ref": "Abbildung"})
    assert "Abbildung~" in prefix


def test_figure_caption_prefix_empty_without_key_or_id():
    from studium.authoring.render import _figure_caption_prefix

    assert _figure_caption_prefix({}, {"figure_ref": "figura"}) == ""


def test_emit_prose_resolves_figure_reference():
    lines = emit_prose("Como muestra la {{fig:flujo}}, la velocidad cae.", figure_ref="figura")
    joined = "\n".join(lines)
    assert r"figura~\ref{fig:flujo}" in joined
    assert "{{fig:" not in joined


def test_emit_prose_leaves_marker_literal_without_label():
    lines = emit_prose("Ver {{fig:flujo}}.")
    joined = "\n".join(lines)
    assert r"\{\{" in joined
    assert r"\ref" not in joined


def test_figure_reference_key_is_lowercased_for_the_label():
    from studium.authoring.render import _figure_label_key

    assert _figure_label_key("Flujo-Tuberia") == "flujo-tuberia"
    assert _figure_label_key("FIG-0001") == "fig-0001"


# ---------------------------------------------------------------------------
# Integration: figure keys, unresolved references, uncited figures
# ---------------------------------------------------------------------------


def _figure_project(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _project(tmp_path)
    dispatch(
        "studium_blueprint_store",
        {"sections": [{"id": "ch", "title": "Chapter"}]},
        session=session,
    )
    excerpts = _excerpts(session)
    dispatch(
        "studium_paragraph_record",
        {
            "section": "ch",
            "text": "Como se ve en la {{fig:flujo}}, la presión sube con la profundidad.",
            "excerpts": excerpts,
        },
        session=session,
    )
    return session, root, excerpts


class TestFigureReferences:
    def test_a_key_is_stored_and_reported(self, tmp_path, monkeypatch):
        session, _root, excerpts = _figure_project(tmp_path, monkeypatch)
        created = dispatch(
            "studium_figure_record",
            {
                "section": "ch",
                "caption": "Perfil de presión.",
                "kind": "tikz",
                "source": r"\draw (0,0) -- (1,1);",
                "excerpts": excerpts,
                "key": "flujo",
            },
            session=session,
        )
        assert created["status"] == "recorded", created
        assert created["figure"]["key"] == "flujo"

    def test_invalid_key_is_rejected(self, tmp_path, monkeypatch):
        session, _root, excerpts = _figure_project(tmp_path, monkeypatch)
        bad = dispatch(
            "studium_figure_record",
            {
                "section": "ch",
                "caption": "Perfil.",
                "kind": "tikz",
                "source": r"\draw (0,0) -- (1,1);",
                "excerpts": excerpts,
                "key": "Not A Slug",
            },
            session=session,
        )
        assert bad["status"] == "figure.key_invalid"

    def test_duplicate_key_is_rejected(self, tmp_path, monkeypatch):
        session, _root, excerpts = _figure_project(tmp_path, monkeypatch)
        first = dispatch(
            "studium_figure_record",
            {"section": "ch", "caption": "A.", "kind": "tikz", "source": r"\draw (0,0)--(1,1);", "excerpts": excerpts, "key": "flujo"},
            session=session,
        )
        assert first["status"] == "recorded", first
        second = dispatch(
            "studium_figure_record",
            {"section": "ch", "caption": "B.", "kind": "tikz", "source": r"\draw (0,0)--(2,2);", "excerpts": excerpts, "key": "flujo"},
            session=session,
        )
        assert second["status"] == "figure.key_taken"

    def test_missing_reference_is_reported(self, tmp_path, monkeypatch):
        from studium.authoring.figures import unresolved_figure_references

        _session, root, _ = _figure_project(tmp_path, monkeypatch)
        items = unresolved_figure_references(root)
        assert [item["key"] for item in items] == ["flujo"]
        assert items[0]["reason"] == "missing"

    def test_unchecked_reference_is_reported(self, tmp_path, monkeypatch):
        from studium.authoring.figures import unresolved_figure_references

        session, root, excerpts = _figure_project(tmp_path, monkeypatch)
        dispatch(
            "studium_figure_record",
            {"section": "ch", "caption": "Perfil.", "kind": "tikz", "source": r"\draw (0,0)--(1,1);", "excerpts": excerpts, "key": "flujo"},
            session=session,
        )
        items = unresolved_figure_references(root)
        assert [item["reason"] for item in items] == ["unchecked"]

    def test_reference_resolves_after_record_with_key(self, tmp_path, monkeypatch):
        from studium.authoring.figures import figure_reference_map, referenced_figure_keys

        session, root, excerpts = _figure_project(tmp_path, monkeypatch)
        dispatch(
            "studium_figure_record",
            {"section": "ch", "caption": "Perfil.", "kind": "tikz", "source": r"\draw (0,0)--(1,1);", "excerpts": excerpts, "key": "flujo"},
            session=session,
        )
        assert referenced_figure_keys(root) == ["flujo"]
        assert "flujo" in figure_reference_map(root)


class TestFigureRendering:
    """The rendered LaTeX numbers the figure and links the reference to it."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        from studium.authoring import render as render_mod

        self.session, self.root, excerpts = _figure_project(tmp_path, monkeypatch)
        dispatch(
            "studium_figure_record",
            {
                "section": "ch",
                "caption": "Perfil de presión con la profundidad.",
                "kind": "tikz",
                "source": r"\draw (0,0) -- (2,2);",
                "excerpts": excerpts,
                "key": "flujo",
            },
            session=self.session,
        )
        # Force the drawing to count as rendered without invoking pdflatex.
        monkeypatch.setattr(render_mod, "_checked_output", lambda root, record: "figures/FIG-x/figure.pdf")
        rendered = render_draft(self.root)
        assert rendered["status"] in ("rendered", "compiler_missing", "incomplete"), rendered
        self.tex = (self.root / "latex" / "draft.tex").read_text(encoding="utf-8")

    def test_counter_declared_in_preamble(self):
        assert r"\newcounter{studiumfigure}" in self.tex

    def test_figure_label_uses_the_stable_key(self):
        assert r"\label{fig:flujo}" in self.tex

    def test_prose_reference_is_numbered_by_latex(self):
        assert r"figura~\ref{fig:flujo}" in self.tex

    def test_caption_carries_the_localized_number(self):
        assert r"Figura~\thestudiumfigure." in self.tex




def test_mixed_ascii_subscript_and_unicode_power():
    from studium.authoring.render import render_text_run

    cases = [
        ("V_entrada²", "V_{entrada}^{2}"),
        ("V_salida³", "V_{salida}^{3}"),
        ("V_entrada⁻²", "V_{entrada}^{-2}"),
    ]

    for expression, expected in cases:
        rendered = render_text_run(
            "La expresión es " + expression + " y continúa."
        )
        assert expected in rendered, rendered


def test_plain_ascii_subscript_remains_unchanged():
    from studium.authoring.render import render_text_run

    rendered = render_text_run("p_man = ρ g h")

    assert "p_man" in rendered


def _chapter_problem_setup(tmp_path, monkeypatch):
    """Synthetic data only: two chapters both start their exercise count at one."""
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    monkeypatch.setattr("studium.authoring.render.find_engine", lambda: None)
    session, root = _project(tmp_path)
    dispatch("studium_blueprint_store", {"sections": [{"id": "presion", "title": "Presión"}, {"id": "energia", "title": "Energía"}]}, session=session)
    excerpts = _excerpts(session)
    ids = []
    # Author the second chapter first, to exercise blueprint ordering.
    for section in ("energia", "presion"):
        result = dispatch(
            "studium_problem_record",
            {"section": section, "prompt": f"Synthetic practice fixture for {section}.", "expected": "6", "excerpts": excerpts, "role": "practice", "difficulty": "FOUNDATIONAL", "problem_type": "MULTI_STEP"},
            session=session,
        )
        assert result["status"] == "recorded", result
        ids.append(result["problem"]["id"])
    return session, root, ids


def test_solution_appendix_matches_statements_by_chapter_and_stable_identifier(tmp_path, monkeypatch):
    from studium.authoring.languages import active_language, messages
    from studium.authoring.render import _exercise_box, _solution_lines

    _session, root, ids = _chapter_problem_setup(tmp_path, monkeypatch)
    language = active_language(root)
    appendix = "\n".join(_solution_lines(root, messages(language), language))
    assert appendix.index(r"\section{Presión}") < appendix.index(r"\section{Energía}")
    for section, identifier in zip(("energia", "presion"), ids, strict=True):
        statement = "\n".join(_exercise_box(root, section, language))
        assert f"1 [{identifier}]" in statement
        assert f"Ejercicio 1 [{identifier}]" in appendix
        assert "Básico" in statement and "Desarrollo por pasos" in statement
        assert "FOUNDATIONAL" not in statement and "MULTI" not in statement


def test_solution_appendix_omits_stale_problem_and_keeps_unsolved_count(tmp_path, monkeypatch):
    from studium.authoring.languages import active_language, messages
    from studium.authoring.render import _solution_lines

    _session, root, ids = _chapter_problem_setup(tmp_path, monkeypatch)
    from studium.authoring.render import problem_result_current

    original = problem_result_current
    monkeypatch.setattr("studium.authoring.render.problem_result_current", lambda path, record: record.get("id") != ids[0] and original(path, record))
    language = active_language(root)
    appendix = "\n".join(_solution_lines(root, messages(language), language))
    assert ids[0] not in appendix
    assert ids[1] in appendix
    assert "1 ejercicio todavía sin solución comprobada" in appendix
    assert r"\section{Energía}" not in appendix


def test_replayed_calculations_stay_in_their_own_chapter(tmp_path, monkeypatch):
    from studium.authoring.languages import active_language, messages
    from studium.authoring.render import _solution_lines

    session, root, _ids = _chapter_problem_setup(tmp_path, monkeypatch)
    first_check = dispatch("studium_computation_check", {"expression": "7.1*8", "result": "56.8", "section": "presion"}, session=session)
    assert first_check["status"] == "replayed", first_check
    second_check = dispatch("studium_computation_check", {"expression": "8.1*9", "result": "72.9", "section": "energia"}, session=session)
    assert second_check["status"] == "replayed", second_check
    language = active_language(root)
    appendix = "\n".join(_solution_lines(root, messages(language), language))
    first, second = appendix.split(r"\section{Energía}")
    assert "56" in first and "72" not in first
    assert "72" in second and "56" not in second
    assert appendix.count(r"\subsection*{Cálculos reproducidos}") == 2


def test_native_draft_with_fractional_units_and_equation_leadins_compiles(tmp_path, monkeypatch):
    import shutil
    import subprocess

    engine = shutil.which("pdflatex")
    if engine is None:
        pytest.skip("no pdflatex engine")
    from studium.authoring.excerpts import excerpts_by_id

    session, root, ids = _chapter_problem_setup(tmp_path, monkeypatch)
    excerpts = list(excerpts_by_id(root))[:2]
    for section in ("presion", "energia"):
        result = dispatch("studium_paragraph_record", {"section": section, "text": "Aplicando el balance:\n" + r"\[F=ma\]", "excerpts": excerpts}, session=session)
        assert result["status"] == "recorded", result
    for symbol, units in (("f", "1/s"), ("q", "kg/(s*K^0.5)")):
        result = dispatch("studium_notation_record", {"section": "presion", "symbol": symbol, "meaning": "Synthetic unit fixture", "units": units}, session=session)
        assert result["status"] == "recorded", result
    before = {path: path.read_bytes() for path in root.rglob("*.jsonl")}
    render_draft(root)
    assert before == {path: path.read_bytes() for path in before}
    tex = (root / "latex/draft.tex").read_text()
    assert r"\section{Aplicando el balance:}" not in tex
    assert r"\mathrm{K}^{\frac{-1}{2}}" in tex
    assert all(f"Ejercicio 1 [{identifier}]" in tex for identifier in ids)
    for _ in range(2):
        compiled = subprocess.run([engine, "-interaction=nonstopmode", "-halt-on-error", "-no-shell-escape", "draft.tex"], cwd=root / "latex", capture_output=True, text=True, errors="replace")
        assert compiled.returncode == 0, compiled.stdout[-4000:]
    assert (root / "latex/draft.pdf").read_bytes().startswith(b"%PDF-")


def test_replayed_computation_in_solutions_uses_typeset_math_not_raw_python(tmp_path, monkeypatch):
    session, root, _ids = _chapter_problem_setup(tmp_path, monkeypatch)
    from studium.authoring.computation import evaluate
    expr = "101325*(1 - 0.0065*11000/288.15)**5.25588"
    expected = f"{float(evaluate(expr)):.12g}"
    check = dispatch(
        "studium_computation_check",
        {"expression": expr, "result": expected, "section": "presion"},
        session=session,
    )
    assert check["status"] == "replayed", check
    from studium.authoring.languages import book_language, messages
    from studium.authoring.render import _solution_lines
    lang = book_language(root)
    assert lang is not None
    appendix = "\n".join(_solution_lines(root, messages(lang), lang))
    assert "**" not in appendix
    assert r"\cdot" in appendix


def test_audit_lines_separate_paragraphs_with_blank_lines(tmp_path, monkeypatch):
    _session, root = _full_setup(tmp_path, monkeypatch)
    render_draft(root)
    tex = (root / "latex" / "draft.tex").read_text(encoding="utf-8")
    assert "\n\n\\noindent ¶1:" in tex
    assert "\n\n\\noindent ¶2:" in tex
