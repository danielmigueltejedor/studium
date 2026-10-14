"""End-to-end scientific review through MCP dispatch and CLI."""

import json

from test_professional_math import _setup, _structured_solution

from studium.authoring.problems import list_problems
from studium.cli.app import main
from studium.mcp.server import dispatch


def _record_problem(tmp_path, monkeypatch):
    session, root, excerpts = _setup(tmp_path, monkeypatch)

    recorded = dispatch(
        "studium_problem_record",
        {
            "section": "hidrostatica",
            "prompt": "Calcula la presión hidrostática a 10 metros.",
            "expected": "97903.8",
            "excerpts": excerpts,
            "role": "worked",
            "problem_type": "MULTI_STEP",
            "solution": _structured_solution(),
        },
        session=session,
    )

    assert recorded["status"] == "recorded", recorded

    return session, root, recorded["problem"]["id"]


def test_real_mcp_dispatch_returns_scientific_report(
    tmp_path,
    monkeypatch,
):
    session, root, problem_id = _record_problem(
        tmp_path,
        monkeypatch,
    )

    before = list_problems(root)

    reviewed = dispatch(
        "studium_problem_scientific_review",
        {
            "id": problem_id,
            "expected_value": 97903.8,
            "expected_unit": "Pa",
        },
        session=session,
    )

    assert reviewed["status"] == "ok", reviewed
    assert reviewed["problem_id"] == problem_id
    assert reviewed["advisory"] is True
    assert reviewed["stored_content_modified"] is False

    report = reviewed["report"]

    assert report["status"] == "UNVERIFIED"
    assert report["outputs"]["human_review_required"] is True

    # The review must not modify stored problems.
    assert list_problems(root) == before


def test_real_cli_returns_same_advisory_report(
    tmp_path,
    monkeypatch,
    capsys,
):
    _session, root, problem_id = _record_problem(
        tmp_path,
        monkeypatch,
    )

    before = list_problems(root)

    exit_code = main(
        [
            "problem",
            "scientific-review",
            problem_id,
            "--expected-value",
            "97903.8",
            "--expected-unit",
            "Pa",
            "--project",
            str(root),
            "--json",
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0, output

    result = json.loads(output)

    assert result["status"] == "ok"
    assert result["problem_id"] == problem_id
    assert result["report"]["status"] == "UNVERIFIED"
    assert result["advisory"] is True

    assert list_problems(root) == before


def test_mcp_review_rejects_nonexistent_problem(
    tmp_path,
    monkeypatch,
):
    session, _root, _problem_id = _record_problem(
        tmp_path,
        monkeypatch,
    )

    result = dispatch(
        "studium_problem_scientific_review",
        {"id": "PRB-9999"},
        session=session,
    )

    assert result["status"] == "problem.not_found"
