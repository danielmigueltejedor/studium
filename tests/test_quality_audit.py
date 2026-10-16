"""An integrated audit reports failures and uncertainty without editing books."""

import json
from copy import deepcopy

import pytest
from test_professional_math import _open_source, _setup, _structured_solution

from studium.authoring.publishing import report_markdown
from studium.authoring.quality_audit import book_quality_audit, solution_gaps
from studium.cli.app import main
from studium.mcp.server import dispatch, tool_names
from studium.storage.records import PROBLEMS, append_jsonl, fold_by_id


def _record(session, excerpts, solution, expected="97903.8"):
    result = dispatch(
        "studium_problem_record",
        {
            "section": "hidrostatica",
            "prompt": "Calculate the pressure.",
            "expected": expected,
            "excerpts": excerpts,
            "role": "worked",
            "solution": solution,
        },
        session=session,
    )
    assert result["status"] == "recorded", result
    return result["problem"]["id"]


def _snapshot(root):
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_distinct_irrelevant_sources_are_not_semantic_corroboration(tmp_path, monkeypatch):
    session, root, excerpts = _setup(tmp_path, monkeypatch)
    excerpts = [
        _open_source(
            session, "Synthetic unrelated A", "https://open.example/unrelated-a", "A triangle has three vertices."
        ),
        _open_source(
            session, "Synthetic unrelated B", "https://open.example/unrelated-b", "A square has four vertices."
        ),
    ]
    problem = _record(session, excerpts, _structured_solution())
    dispatch("studium_problem_check", {"id": problem}, session=session)
    before = _snapshot(root)
    report = dispatch("studium_book_quality_audit", {}, session=session)
    assert "studium_book_quality_audit" in tool_names()
    support = next(issue for issue in report["issues"] if issue["type"] == "claim_support_unestablished")
    assert support["evidence"]["source_diversity"] is True
    assert support["evidence"]["semantic_support"] == "not_established"
    assert support["severity"] == "REVIEW_REQUIRED"
    assert report["scientific_validity"] == "not_established"
    assert _snapshot(root) == before
    assert report == book_quality_audit(root)  # Stable finding ids, no audit timestamp churn.
    assert "REVIEW_REQUIRED" in report_markdown(report)


@pytest.mark.parametrize("wrong_unit", ["m", "N"])
def test_replayed_arithmetic_does_not_hide_dimensional_errors(tmp_path, monkeypatch, wrong_unit):
    session, root, excerpts = _setup(tmp_path, monkeypatch)
    solution = _structured_solution()
    solution["steps"][-1]["unit"] = wrong_unit
    problem = _record(session, excerpts, solution)
    checked = dispatch("studium_problem_check", {"id": problem}, session=session)
    assert checked["steps_reproduced"] is True
    report = book_quality_audit(root)
    failures = [issue for issue in report["issues"] if issue["type"] == "dimensional_check_failed"]
    assert failures and failures[0]["severity"] == "ERROR"
    assert report["scientific_validity"] == "not_established"


def test_reproducible_but_inapplicable_model_requires_expert_review(tmp_path, monkeypatch):
    session, root, excerpts = _setup(tmp_path, monkeypatch)
    solution = _structured_solution()
    solution["assumptions"] = ["Apply the static-fluid law to a rapidly accelerating compressible flow."]
    problem = _record(session, excerpts, solution)
    dispatch("studium_problem_check", {"id": problem}, session=session)
    report = book_quality_audit(root)
    review = next(issue for issue in report["issues"] if issue["type"] == "scientific_review_required")
    assert review["severity"] == "REVIEW_REQUIRED"
    assert review["evidence"]["model_reproduction"] == "COMPUTATION_REPRODUCED"
    assert review["evidence"]["scientific_validity"] == "not_established"


def test_structural_completeness_is_not_a_word_count_score():
    solution = {"result": "1", "interpretation": "very long " * 1000, "steps": [{"expression": "1+0", "expected": "1"}]}
    gaps = solution_gaps(solution)
    assert {"given", "unknown", "model", "assumptions", "step_explanations", "symbolic_steps", "step_units"} <= set(
        gaps
    )
    assert "interpretation" not in gaps
    assert solution_gaps(_structured_solution()) == []


def test_changed_problem_fingerprint_is_reported(tmp_path, monkeypatch):
    session, root, excerpts = _setup(tmp_path, monkeypatch)
    problem = _record(session, excerpts, _structured_solution())
    dispatch("studium_problem_check", {"id": problem}, session=session)
    record = deepcopy(fold_by_id(root / PROBLEMS)[0])
    record["expected"] = "123"
    append_jsonl(root / PROBLEMS, record)
    report = book_quality_audit(root)
    assert any(issue["type"] == "problem_unchecked_or_stale" for issue in report["issues"])


def test_audit_cli_exports_json_and_markdown(tmp_path, monkeypatch, capsys):
    _, root, _ = _setup(tmp_path, monkeypatch)
    assert main(["quality-audit", "--project", str(root)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "ok" and report["stored_content_modified"] is False
    assert main(["quality-audit", "--project", str(root), "--format", "markdown"]) == 0
    assert "# Studium quality report" in capsys.readouterr().out


def test_renderer_maps_records_and_preserves_editorial_corrections(tmp_path, monkeypatch):
    from studium.authoring.render import find_engine

    if find_engine() is None:
        pytest.skip("LaTeX unavailable")
    session, root, excerpts = _setup(tmp_path, monkeypatch)
    paragraph = dispatch(
        "studium_paragraph_record",
        {"section": "hidrostatica", "text": "Original text.", "excerpts": excerpts},
        session=session,
    )["paragraph"]["id"]
    dispatch(
        "studium_paragraph_replace",
        {"id": paragraph, "text": "[E2-C05:w_perfil_u_abierto] y σ = F/A.", "excerpts": excerpts},
        session=session,
    )
    _record(session, excerpts, _structured_solution())
    # Render twice: immutable academic records and stable identifiers.
    before = {path: data for path, data in _snapshot(root).items() if not path.startswith("latex/")}
    for _ in range(2):
        rendered = dispatch("studium_render", {}, session=session)
        assert rendered["status"] == "rendered", rendered
        report = json.loads((root / rendered["editorial_report"]).read_text())
        assert report["compiled"] is True
        assert any(entry["record"] == paragraph for entry in report["source_map"])
        assert report["counts"]["ERROR"] == 0
        assert (root / "latex" / "draft.quality.md").is_file()
    after = {path: data for path, data in _snapshot(root).items() if not path.startswith("latex/")}
    assert before == after


def test_stale_editorial_report_is_not_reused(tmp_path, monkeypatch):
    import hashlib

    _, root, _ = _setup(tmp_path, monkeypatch)
    latex = root / "latex"
    latex.mkdir(exist_ok=True)
    (latex / "draft.tex").write_text("new revision")
    (latex / "draft.quality.json").write_text(
        json.dumps(
            {
                "document_sha256": hashlib.sha256(b"old revision").hexdigest(),
                "issues": [{"severity": "ERROR", "type": "old_failure"}],
            }
        )
    )
    report = book_quality_audit(root)
    assert any(issue["type"] == "editorial_report_stale" for issue in report["issues"])
    assert not any(issue["type"] == "old_failure" for issue in report["issues"])


def test_bare_physical_result_without_units_is_incomplete():
    solution = _structured_solution()
    solution["result"] = "97903.8"
    assert "result_units" in solution_gaps(solution)
    solution["steps"][-1]["unit"] = "dimensionless"
    assert "result_units" not in solution_gaps(solution)
