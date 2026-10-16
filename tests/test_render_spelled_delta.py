"""Prose such as ``delta E_int = Q - W`` is typeset as a Delta with a word subscript."""

from __future__ import annotations

from studium.authoring.render import render_text_run


def test_spelled_delta_becomes_a_delta() -> None:
    assert render_text_run("so delta S = Q/T holds") == r"so \(\Delta S = Q/T\) holds"


def test_spelled_delta_keeps_its_subscript() -> None:
    assert render_text_run("delta U_1 = Q - W") == r"\(\Delta U_1 = Q - W\)"


def test_prose_delta_is_left_alone() -> None:
    assert render_text_run("a delta wing is a shape") == "a delta wing is a shape"
