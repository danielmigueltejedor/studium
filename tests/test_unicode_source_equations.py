"""An excerpt typed with Unicode Greek letters states the same relation as the LaTeX the book writes."""

import pytest

from studium.authoring.grounding import _chain_relations, _stated_in

_BODY = "In solid mechanics, the shear modulus or modulus of rigidity G = τ / γ = E / [2(1 + ν)] is a measure of shear stiffness."


def test_a_chain_in_prose_states_every_pair_of_its_sides():
    pairs = _chain_relations(_BODY)
    assert "G = \\tau / \\gamma" in pairs
    assert "G = E / (2(1 + \\nu))" in pairs
    assert "\\tau / \\gamma = E / (2(1 + \\nu))" in pairs


@pytest.mark.parametrize(
    "statement",
    [r"G = \tau/\gamma", r"G = \frac{E}{2\,(1+\nu)}", r"G = E/[2(1+\nu)]", r"\gamma = \tau/G"],
)
def test_the_latex_relation_is_found_in_the_unicode_excerpt(statement):
    assert _stated_in(statement, _BODY)


@pytest.mark.parametrize("statement", [r"G = \frac{E}{3(1+\nu)}", r"G = E/(2(1-\nu))", r"G = \tau\gamma"])
def test_a_different_relation_is_not_found(statement):
    assert not _stated_in(statement, _BODY)
