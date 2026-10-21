"""Legacy entry points must not bypass the untrusted-code boundary."""

import json
from unittest.mock import Mock

import pytest

from studium.authoring.figures import check_figure
from studium.authoring.problems import check_problem
from studium.cli.app import main
from studium.mcp.server import dispatch, handle, open_workspace
from studium.storage.records import FIGURES, PROBLEMS, append_jsonl, fold_by_id
from studium.verification.execution import ReviewedHostExecution, execution_input_sha256, host_execution_authorized


def _book(tmp_path):
    session = open_workspace(str(tmp_path))
    assert session is not None
    assert dispatch("studium_project_create", {"slug": "rust", "topic": "Rust"}, session=session)["status"] == "created"
    assert dispatch("studium_blueprint_store", {"sections": [{"id": "basics", "title": "Basics"}]}, session=session)["status"] == "recorded"
    return session, tmp_path / "rust"


def _rust(session):
    result = dispatch("studium_problem_record", {
        "section": "basics", "prompt": "Check arithmetic.",
        "source_text": "#[test] fn arithmetic() { assert_eq!(2 + 2, 4); }",
        "invocation": ["rustc", "--test", "main.rs"],
    }, session=session)
    assert result["status"] == "recorded", result
    return result["problem"]["id"]


def _figure(session):
    source = dispatch("studium_public_source_record", {"title": "Synthetic figure source", "url": "https://example.org/figure"}, session=session)
    excerpt = dispatch("studium_excerpt_record", {
        "source_id": source["candidate"]["id"], "url": "https://example.org/figure", "text": "Synthetic data for a fixture.",
    }, session=session)
    result = dispatch("studium_figure_record", {
        "section": "basics", "caption": "Synthetic fixture.", "kind": "python",
        "source": "import sys\nprint(sys.modules['__main__'].__dict__.keys())",
        "excerpts": [excerpt["excerpt"]["id"]],
    }, session=session)
    assert result["status"] == "recorded", result
    return result["figure"]["id"]


@pytest.mark.parametrize("kind", ["problem", "figure"])
def test_mcp_default_refuses_before_any_launch_or_write(tmp_path, monkeypatch, kind):
    session, root = _book(tmp_path)
    identifier = _rust(session) if kind == "problem" else _figure(session)
    runner = Mock(side_effect=AssertionError("untrusted source must never execute"))
    monkeypatch.setattr("studium.authoring.problems._three_runs", runner)
    monkeypatch.setattr("studium.authoring.figures._run_python", runner)
    path = root / (PROBLEMS if kind == "problem" else FIGURES)
    record = dict(fold_by_id(path)[0])
    record["trusted"] = True
    record["execution"] = {"kind": "reviewed_author_owned_host_execution", "reviewer": "model", "isolated": True}
    append_jsonl(path, record)
    snapshot = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    # Document metadata and unknown JSON fields must never grant a capability.
    for extra in ({}, {"trusted": True, "execution": {"reviewer": "model", "reason": "approved"}}):
        result = dispatch(f"studium_{kind}_check", {"id": identifier, **extra}, session=session)
        assert result["status"] == "execution.isolation_required"
        assert result["checked"] is False and result["correct"] is False
        assert result["classification"] == "UNVERIFIED"
        assert result["runs"] == [] and len(result["source_sha256"]) == 64
        assert result[kind]["correct"] is False
    runner.assert_not_called()
    assert snapshot == {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    wire = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": f"studium_{kind}_check", "arguments": {"id": identifier},
    }}, session=session)
    assert wire["result"]["isError"] is True


@pytest.mark.parametrize("kind", ["problem", "figure"])
def test_cli_refuses_untrusted_execution(tmp_path, monkeypatch, capsys, kind):
    session, root = _book(tmp_path)
    identifier = _rust(session) if kind == "problem" else _figure(session)
    monkeypatch.setattr("subprocess.run", Mock(side_effect=AssertionError("must not launch")))
    assert main([kind, "check", identifier, "--project", str(root), "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "execution.isolation_required"


def test_authorization_is_exact_and_is_not_serializable_metadata():
    source, invocation = "print(1)", ["python", "figure"]
    approval = ReviewedHostExecution(execution_input_sha256(source, invocation), "Fixture author", "Reviewed local fixture")
    assert host_execution_authorized(source, invocation, approval)
    assert not host_execution_authorized(source + "\n", invocation, approval)
    assert not host_execution_authorized(source, [*invocation, "changed"], approval)
    assert not host_execution_authorized(source, invocation, None)
    assert not host_execution_authorized(source, invocation, {"input_sha256": approval.input_sha256})  # type: ignore[arg-type]
    for digest, reviewer, reason in (("bad", "x", "x"), ("a" * 64, "", "x"), ("a" * 64, "x", "")):
        with pytest.raises(ValueError):
            ReviewedHostExecution(digest, reviewer, reason)


@pytest.mark.parametrize("kind", ["problem", "figure"])
def test_wrong_source_authorization_still_refuses(tmp_path, monkeypatch, kind):
    session, root = _book(tmp_path)
    identifier = _rust(session) if kind == "problem" else _figure(session)
    approval = ReviewedHostExecution(execution_input_sha256("other source", ["python", "figure"]), "Author", "Different input")
    monkeypatch.setattr("subprocess.run", Mock(side_effect=AssertionError("must not launch")))
    result = (check_problem if kind == "problem" else check_figure)(root, identifier, execution=approval)
    assert result["status"] == "execution.isolation_required"


def test_cargo_graph_cannot_be_authorized_by_a_single_source(tmp_path, monkeypatch):
    from studium.authoring.problems import _check_rust

    session, root = _book(tmp_path)
    identifier = _rust(session)
    record = next(item for item in fold_by_id(root / PROBLEMS) if item["id"] == identifier)
    record["invocation"] = ["cargo", "test", "--offline"]
    approval = ReviewedHostExecution(execution_input_sha256(str(record["source_text"]), ["cargo", "test", "--offline"]), "Author", "One file only")
    runner = Mock(side_effect=AssertionError("must not launch a build graph"))
    monkeypatch.setattr("studium.authoring.problems._three_runs", runner)
    assert _check_rust(root, record, execution=approval)["status"] == "execution.isolation_required"
    runner.assert_not_called()


def test_python_denial_preserves_previous_artifact(tmp_path):
    session, root = _book(tmp_path)
    identifier = _figure(session)
    output = root / "figures" / identifier / "figure.png"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"previous reviewed output")
    assert check_figure(root, identifier)["status"] == "execution.isolation_required"
    assert output.read_bytes() == b"previous reviewed output"
    assert fold_by_id(root / FIGURES)[0]["status"] == "unchecked"


def test_orchestrator_keeps_execution_pending_after_a_pdf(tmp_path, monkeypatch):
    from studium.authoring import book_next as orchestrator

    session, root = _book(tmp_path)
    rust = _rust(session)
    figure = _figure(session)
    (root / "latex").mkdir()
    (root / "latex" / "draft.pdf").write_bytes(b"%PDF-existing-draft")
    monkeypatch.setattr(orchestrator, "_book_next", lambda _root: {"tool": None, "status": "ok", "reason": "Draft exists", "released": False})
    for _ in range(2):
        result = orchestrator.book_next(root)
        assert result["tool"] is None
        assert result["status"] == "execution.isolation_required"
        assert {item["id"] for item in result["pending_execution"]} == {rust, figure}
        assert all(item["verification"] == "UNVERIFIED" for item in result["pending_execution"])
        assert result["released"] is False


def test_python_reference_does_not_recommend_an_impossible_check(tmp_path, monkeypatch):
    from studium.authoring import book_next as orchestrator

    monkeypatch.setattr(orchestrator, "unresolved_figure_references", lambda _root: [{"paragraph": "PAR-0001", "reason": "unchecked", "key": "plot"}])
    monkeypatch.setattr(orchestrator, "figure_reference_map", lambda _root: {"plot": {"id": "FIG-0001", "kind": "python"}})
    assert orchestrator._pending_figure_reference({}, tmp_path) is None
