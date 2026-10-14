"""End-to-end tests for book substitution audits through MCP and CLI."""

import json

from test_scientific_review_integration import _record_problem

from studium.authoring.problems import list_problems
from studium.cli.app import main
from studium.mcp.catalog import tool_names
from studium.mcp.server import dispatch


def test_book_audit_is_registered():
    assert "studium_book_substitution_audit" in tool_names()


def test_book_audit_via_mcp(tmp_path, monkeypatch):
    session, root, _problem_id = _record_problem(
        tmp_path, monkeypatch
    )

    before = list_problems(root)

    result = dispatch(
        "studium_book_substitution_audit",
        {"offset": 0, "limit": 10},
        session=session,
    )

    assert result["status"] == "ok", result
    assert result["total_problems"] == 1
    assert result["examined"] == 1
    assert result["next_offset"] is None
    assert result["advisory"] is True
    assert result["stored_content_modified"] is False
    assert list_problems(root) == before


def test_book_audit_via_cli(tmp_path, monkeypatch, capsys):
    _session, root, _problem_id = _record_problem(
        tmp_path, monkeypatch
    )

    before = list_problems(root)

    code = main([
        "problem",
        "audit-substitutions",
        "--project",
        str(root),
        "--offset",
        "0",
        "--limit",
        "10",
        "--json",
    ])

    output = capsys.readouterr().out

    assert code == 0, output

    result = json.loads(output)

    assert result["status"] == "ok"
    assert result["total_problems"] == 1
    assert result["examined"] == 1
    assert result["stored_content_modified"] is False
    assert list_problems(root) == before


def test_invalid_page_size_is_rejected_by_mcp(
    tmp_path, monkeypatch
):
    session, _root, _problem_id = _record_problem(
        tmp_path, monkeypatch
    )

    result = dispatch(
        "studium_book_substitution_audit",
        {"limit": 51},
        session=session,
    )

    assert result["status"] == "mcp.invalid_input"
