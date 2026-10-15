"""A sentence that rules a value out does not assert it."""

from __future__ import annotations

from studium.authoring.audit import _asserted_quantities


def test_forbidden_value_is_not_an_assertion() -> None:
    text = "Kelvin-Planck forbids Qc = 0, so the efficiency is below one. The density is 2."
    assert _asserted_quantities(text) == [("density", "2")]


def test_plain_statement_is_still_asserted() -> None:
    assert _asserted_quantities("The pressure is 101. Heat flows.") == [("pressure", "101")]
