"""Regression tests for the Unicode-to-LaTeX math renderer.

The renderer must typeset the inline mathematics a STEM author actually writes
in a draft paragraph: nonspaced/multi-letter subscripts, runs of Unicode
super- and subscripts, radicals, Greek letters, and short inline formulas. It
must never emit LaTeX that pdflatex cannot parse (a double script, a ``{U+...}``
placeholder inside math, or unbalanced braces).
"""

import re

import pytest

from studium.authoring.render import latex_escape, render_text_run

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _math_groups(rendered: str) -> list[str]:
    return re.findall(r"\\\((.*?)\\\)|\\\[(.*?)\\\]", rendered, flags=re.DOTALL)


def _assert_balanced(rendered: str) -> None:
    for inline, display in _math_groups(rendered):
        text = inline or display
        assert text.count("{") == text.count("}"), rendered
        assert "U+" not in text, rendered
        assert "}^{-}" not in text and "}_{-}" not in text, rendered
        assert "^{}^{" not in text and "_{}_{" not in text, rendered


# ---------------------------------------------------------------------------
# Multi-letter and nonspaced subscripts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("p_{man} = ρ g h", r"\(p_{man} = \rho g h\)"),
        ("p_man = ρ_fluido g h", r"\(p_man = \rho_fluido g h\)"),
        ("V_{desplazado} = m/ρ", r"\(V_{desplazado} = m/\rho\)"),
        ("la longitud α_{crit} cierra", r"\(\alpha_{crit}\)"),
    ],
)
def test_multi_letter_subscripts(raw, expected):
    rendered = render_text_run(raw)
    assert expected in rendered
    _assert_balanced(rendered)


def test_multi_letter_word_is_not_pulled_out_of_prose():
    rendered = render_text_run("La densidad ρ del fluido y la relación es clara.")
    assert r"\(\rho\)" in rendered
    assert "densidad" in rendered
    assert "fluido" in rendered


# ---------------------------------------------------------------------------
# Consecutive Unicode scripts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("El orden es 10⁻³ m.", r"10^{-3}"),
        ("μ = 1.8×10⁻⁵ Pa·s", r"1.8\times10^{-5}"),
        ("k_B = 1.38×10⁻²³ J/K", r"1.38\times10^{-23}"),
        ("x² + y² = r²", r"x^{2} + y^{2} = r^{2}"),
        ("H₂O y CO₂", "H_{2}O"),
    ],
)
def test_consecutive_scripts_merge_into_one_group(raw, expected):
    rendered = render_text_run(raw)
    assert expected in rendered
    _assert_balanced(rendered)


def test_leading_script_gets_an_empty_base():
    rendered = render_text_run("La sensibilidad es ⁻¹ y creciente.")
    assert r"{}^{-1}" in rendered
    _assert_balanced(rendered)


# ---------------------------------------------------------------------------
# Radicals
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("La raíz √2 es irracional.", r"\sqrt{2}"),
        ("El número de Froude Fr = v/√(g h).", r"v/\sqrt{g h}"),
        ("El radio r = √(A/π).", r"\sqrt{A/\pi}"),
        ("La raíz cúbica ∛8 = 2.", r"\sqrt[3]{8}"),
        ("La raíz cuarta ∜16 = 2.", r"\sqrt[4]{16}"),
    ],
)
def test_radicals_consume_their_argument(raw, expected):
    rendered = render_text_run(raw)
    assert expected in rendered
    _assert_balanced(rendered)


def test_root_argument_stops_at_the_group():
    rendered = render_text_run("El radio r = √(A/π) y el volumen V = (4/3)πr³.")
    assert r"\(r = \sqrt{A/\pi}\)" in rendered
    assert r"\(V = (4/3)\pi r^{3}\)" in rendered
    _assert_balanced(rendered)


# ---------------------------------------------------------------------------
# Greek letters and extra operators
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("La viscosidad τ = μ (dv/dy).", r"\(\tau = \mu (dv/dy)\)"),
        ("La presión p ∝ la densidad.", r"\(p \propto\)"),
        ("La identidad es ≡ cierta.", r"\(\equiv\)"),
        ("Entonces A ⇒ B.", r"\(A \Rightarrow B\)"),
        ("A → B es una transformación.", r"\(A \to B\)"),
        ("El producto es a⋅b y la razón a÷b.", r"a\cdot b"),
        ("La micra es 1 µm.", r"\mu"),
        ("La integral ∫ f dx y la suma ∑ aᵢ.", r"\int"),
    ],
)
def test_greek_and_operators(raw, expected):
    rendered = render_text_run(raw)
    assert expected in rendered
    _assert_balanced(rendered)


def test_fraction_glyph():
    rendered = render_text_run("La energía es E = ½ m v² y ¾ del total.")
    assert r"E = \frac{1}{2} m v^{2}" in rendered
    assert r"\frac{3}{4}" in rendered
    _assert_balanced(rendered)


def test_dotted_symbols():
    rendered = render_text_run("El caudal másico ṁ = ρ A v es constante.")
    assert r"\dot{m} = \rho A v" in rendered
    _assert_balanced(rendered)


# ---------------------------------------------------------------------------
# Whole inline formulas in a paragraph
# ---------------------------------------------------------------------------


def test_inline_formula_head_joins_the_assignment():
    rendered = render_text_run("El número de Reynolds Re = ρ v D / μ es adimensional.")
    assert r"\(Re = \rho v D / \mu\)" in rendered
    _assert_balanced(rendered)


def test_prose_conjunction_is_not_absorbed_into_the_formula():
    rendered = render_text_run("El radio r = √(A/π) y el volumen es grande.")
    assert r"\(r = \sqrt{A/\pi}\)" in rendered
    assert " y el" in rendered
    _assert_balanced(rendered)


def test_accented_word_is_not_split_into_the_formula():
    rendered = render_text_run("La raíz √2 es irracional.")
    assert rendered.startswith("La raíz ")
    assert r"\(\sqrt{2}\)" in rendered
    _assert_balanced(rendered)


# ---------------------------------------------------------------------------
# latex_escape keeps its old semantics for ASCII
# ---------------------------------------------------------------------------


def test_latex_escape_ascii_is_unchanged():
    assert latex_escape("a_b^c") == r"a\_b\textasciicircum{}c"
    assert latex_escape("10% & $5") == r"10\% \& \$5"
    assert latex_escape("a\\b") == r"a\textbackslash{}b"
    assert latex_escape("{x}") == r"\{x\}"


def test_latex_escape_merges_unicode_scripts():
    assert latex_escape("x⁻²") == r"x\({}^{-2}\)"
    assert latex_escape("ρ₀") == r"\(\rho_{0}\)"


def test_dollar_spans_with_comparisons_and_digit_led_variables_are_math():
    """Regression (Theory of Structures book): "$x > a$" and "$2L/3$" were printed with their dollars."""

    from studium.authoring.render import _dollar_ok

    assert _dollar_ok("x > a")
    assert _dollar_ok("2L/3")
    assert _dollar_ok("0 < x < L")
    assert not _dollar_ok("5")
    assert not _dollar_ok("5 and 10")
