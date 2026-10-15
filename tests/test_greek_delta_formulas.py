"""A written-out or Unicode Delta stays part of the relation it prefixes."""

from __future__ import annotations

import pytest

from studium.authoring.grounding import contains_formula, formulas


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        ("so delta U = -W and any work", ["delta U = -W"]),
        ("the change delta U = Q - W holds", ["delta U = Q - W"]),
        ("entropy Delta S = Q/T at constant T", ["Delta S = Q/T"]),
        ("the energy ΔU = Q − W is conserved", ["ΔU = Q − W"]),
    ],
)
def test_delta_prefix_is_kept(sentence: str, expected: list[str]) -> None:
    assert formulas(sentence) == expected


def test_prose_delta_is_not_pulled_in() -> None:
    assert formulas("a delta wing, then x = 3 * y") == ["x = 3 * y"]


def test_delta_spellings_compare_equal() -> None:
    assert contains_formula("delta U = Q - W", "First law: ΔU = Q − W for a closed system")
    assert contains_formula("ΔU = Q − W", "delta U = Q - W")
    assert not contains_formula("delta U = Q + W", "ΔU = Q − W")


def test_unreadable_symbol_on_left_is_not_a_definition() -> None:
    from studium.authoring.latex_calculus import as_definition

    assert as_definition("ρ x = m", {}) is None
