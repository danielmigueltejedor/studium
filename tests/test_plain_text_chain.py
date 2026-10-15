"""A plain-text chain ``a = b = c`` is read as the links ``a = b`` and ``b = c``."""

from studium.authoring.grounding import math_statements


def test_plain_text_chain_gives_adjacent_links():
    found = math_statements("The efficiency is e = W/Qh = 1 - Qc/Qh for a heat engine.")
    claims = [statement for kind, statement in found if kind == "claim"]
    assert "e = W/Qh" in claims
    assert "W/Qh = 1 - Qc/Qh" in claims
    assert not any(statement.count("=") > 1 for statement in claims)


def test_single_plain_text_relation_is_unchanged():
    found = math_statements("The law is S = Q/T here.")
    assert [statement for _kind, statement in found] == ["S = Q/T"]
