"""Synthetic regressions from a multi-chapter aerospace drafting workflow."""

import sys

import pytest
from test_figures import _PNG, _ready, _topic
from test_professional_math import _setup
from test_scientific_contracts import contract
from test_user_material_excerpts import _book, _excerpt, _intake, _notes
from trusted_execution import checked_figure_fixture

from studium.authoring.figures import _run_python
from studium.authoring.support import citation_blockers, excluded_drafts
from studium.mcp.server import dispatch
from studium.storage.records import EXCERPTS, PUBLIC_BIBLIOGRAPHY, append_jsonl, fold_by_id


def test_python_figure_can_import_json_and_math(tmp_path):
    code, detail = _run_python(
        sys.executable,
        tmp_path,
        tmp_path,
        (
            "import json, math\nfrom pathlib import Path\n"
            'assert json.loads("[4]")[0] == math.sqrt(16)\n'
            f'Path("figure.png").write_bytes(bytes.fromhex("{_PNG}"))\n'
        ),
    )
    assert code == 0, detail
    assert (tmp_path / "figure.png").is_file()


def test_matplotlib_numpy_figure_runs_in_server_environment(tmp_path):
    pytest.importorskip("matplotlib")
    pytest.importorskip("numpy")
    session, root = _topic(tmp_path)
    excerpt_id = _ready(session)
    source = """import json, math
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams["pdf.fonttype"] = 42
from matplotlib.patches import Rectangle
x = np.linspace(0, 2, 20)
f, a = plt.subplots(layout="constrained")
a.plot(x, x**2)
a.add_patch(Rectangle((0, 0), 1, 1, fill=False))
a.set(xlabel="V (m/s)", ylabel=r"$q = \\rho V^2/2$ (Pa)")
f.savefig("figure.png")
f.savefig("figure.pdf")
plt.close(f)
"""
    recorded = dispatch(
        "studium_figure_record",
        {
            "section": "tema-1",
            "caption": "Synthetic curve.",
            "kind": "python",
            "source": source,
            "excerpts": [excerpt_id],
        },
        session=session,
    )
    assert recorded["status"] == "recorded", recorded
    checked = checked_figure_fixture(root, recorded["figure"]["id"])
    assert checked["checked"] is True, checked
    assert checked["figure"]["classification"] == "PENDING"
    assert checked["figure"]["proves_science"] is False
    assert checked["released"] is False
    directory = root / "figures" / recorded["figure"]["id"]
    assert (directory / "figure.png").read_bytes().startswith(b"\x89PNG")
    assert (directory / "figure.pdf").read_bytes().startswith(b"%PDF")


@pytest.mark.parametrize(
    "kind", ["read", "write", "symlink", "import", "network", "process", "eval", "exec", "fake_eval"]
)
def test_python_runner_still_refuses_external_access(tmp_path, kind):
    outside = tmp_path / "private.txt"
    outside.write_text("private content")
    work = tmp_path / "figure"
    work.mkdir()
    (work / "escape").symlink_to(outside)
    sources = {
        "read": f"open({str(outside)!r}).read()",
        "write": f'open({str(outside)!r}, "w").write("changed")',
        "symlink": 'open("escape").read()',
        "import": "import pickle",
        "network": 'import socket\nsocket.create_connection(("127.0.0.1", 9))',
        "process": 'import subprocess\nsubprocess.run(["true"])',
        "eval": 'import builtins\nbuiltins.eval("1+1")',
        "exec": 'import builtins\nbuiltins.exec("x=1")',
        "fake_eval": 'import builtins\n__name__="fontTools.ttLib.tables.otBase"\nbuiltins.eval("1+1")',
    }
    code, detail = _run_python(sys.executable, tmp_path, work, sources[kind])
    assert code != 0, detail
    assert outside.read_text() == "private content"


def test_course_claim_and_contract_accept_explicit_open_supplements(tmp_path, monkeypatch):
    session, root, excerpts = _setup(tmp_path, monkeypatch)
    before = (root / ".studium/state.json").read_bytes()
    claim = dispatch(
        "studium_claim_record",
        {
            "section": "hidrostatica",
            "text": "Synthetic contract anchor.",
            "excerpts": excerpts,
        },
        session=session,
    )
    assert claim["status"] == "recorded", claim
    identifier = claim["claim"]["id"]
    data = contract([{"kind": "identity", "left": "x+x", "right": "2*x"}])
    data["representations"][0]["record"] = identifier
    stored = dispatch("studium_scientific_contract_record", {"claim_id": identifier, "contract": data}, session=session)
    assert stored["status"] == "recorded", stored
    report = dispatch("studium_scientific_contract_report", {}, session=session)
    assert report["contracts"][0]["verification"]["documentary"] == "EVIDENCE_LOCATED"
    assert report["contracts"][0]["verification"]["expert_review"] == "PENDING"
    assert claim["claim"]["classification"] == "PENDING"
    assert all(s.get("course_guide_cited") is not True for s in fold_by_id(root / PUBLIC_BIBLIOGRAPHY))
    assert (root / ".studium/state.json").read_bytes() == before
    assert citation_blockers(root, [], excerpts) == []
    # Revoking the permission invalidates both direct source and excerpt citations.
    source = fold_by_id(root / PUBLIC_BIBLIOGRAPHY)[0]
    source["open_supplement"] = False
    append_jsonl(root / PUBLIC_BIBLIOGRAPHY, source)
    assert citation_blockers(root, [source["id"]], [])
    assert citation_blockers(root, [], excerpts)
    assert excluded_drafts(root)
    assert dispatch("studium_scientific_contract_report", {}, session=session)["contracts"][0]["state"] == "stale"


def test_claim_can_cite_live_local_excerpt_without_promoting_it(tmp_path, monkeypatch):
    session, root = _book(tmp_path, monkeypatch)
    path = _notes(tmp_path)
    sid = _intake(session, path)
    eid = _excerpt(session, sid, path)["excerpt"]["id"]
    claim = dispatch("studium_claim_record", {"text": "Synthetic local anchor.", "excerpts": [eid]}, session=session)
    assert claim["status"] == "recorded", claim
    assert claim["claim"]["classification"] == "PENDING"
    assert "corroboration" not in claim["claim"]
    excerpt = fold_by_id(root / EXCERPTS)[0]
    excerpt["source_sha256"] = "changed-version"
    append_jsonl(root / EXCERPTS, excerpt)
    assert any(b["code"] == "claim.source_changed" for b in citation_blockers(root, [], [eid]))
    assert excluded_drafts(root)


def _generated_problem(session, excerpts):
    stored = dispatch(
        "studium_problem_record",
        {
            "section": "hidrostatica",
            "prompt": "Original synthetic data: mass 2 kg, acceleration 3 m/s². Find the force.",
            "expected": "6",
            "excerpts": excerpts,
            "solution": {
                "given": [
                    {"symbol": "m", "value": "2", "unit": "kg", "meaning": "mass"},
                    {"symbol": "a", "value": "3", "unit": "m/s^2", "meaning": "acceleration"},
                ],
                "unknown": "Force in N",
                "assumptions": ["Point mass, inertial frame."],
                "model": [{"name": "Force", "symbolic": "m*a", "latex": "F=ma"}],
                "steps": [{"text": "Use the generated data.", "expression": "2*3", "expected": "6", "unit": "N"}],
                "result": "F=6 N",
            },
        },
        session=session,
    )
    assert stored["status"] == "recorded", stored
    return stored["problem"]["id"]


def test_generated_integer_step_has_explicit_revision_bound_context(tmp_path, monkeypatch):
    from studium.authoring.audit import _computation_passed
    from studium.authoring.grounding import replayed_computations
    from studium.storage.records import COMPUTATIONS, PROBLEMS

    session, root, excerpts = _setup(tmp_path, monkeypatch)
    pid = _generated_problem(session, excerpts)
    args = {"expression": "2 * 3", "result": "6", "section": "hidrostatica"}
    assert dispatch("studium_computation_check", args, session=session)["status"] == "computation.ungrounded"
    before = (root / ".studium/state.json").read_bytes()
    result = dispatch("studium_computation_check", {**args, "problem_id": pid}, session=session)
    assert result["status"] == "replayed", result
    cid = result["computation"]["id"]
    assert result["computation"]["problem_context"]["id"] == pid
    assert result["computation"]["classification"] == "PENDING"
    assert result["released"] is False
    assert dispatch("studium_computation_check", {"id": cid}, session=session)["status"] == "replayed"
    assert replayed_computations(root)
    assert _computation_passed(root, cid)
    assert (root / ".studium/state.json").read_bytes() == before
    # A changed exercise cannot keep supplying arithmetic evidence to audits or render.
    problem = fold_by_id(root / PROBLEMS)[0]
    problem["prompt"] = "A changed problem statement."
    append_jsonl(root / PROBLEMS, problem)
    history = (root / COMPUTATIONS).read_bytes()
    assert (
        dispatch("studium_computation_check", {"id": cid}, session=session)["status"] == "computation.context_changed"
    )
    assert (
        dispatch("studium_computation_check", {"id": cid, "problem_id": "PRB-unknown"}, session=session)["status"]
        == "computation.context_changed"
    )
    assert not replayed_computations(root)
    assert not _computation_passed(root, cid)
    assert (root / COMPUTATIONS).read_bytes() == history
    assert fold_by_id(root / COMPUTATIONS)[0]["status"] == "replayed"  # append-only history stays intact


@pytest.mark.parametrize(
    "failure", ["missing", "different_step", "different_section", "deleted", "source_revoked", "invalid_id"]
)
def test_generated_context_cannot_anchor_unrelated_or_missing_inputs(tmp_path, monkeypatch, failure):
    from studium.storage.records import COMPUTATIONS, PROBLEMS

    session, root, excerpts = _setup(tmp_path, monkeypatch)
    pid = _generated_problem(session, excerpts)
    args = {"expression": "2*3", "result": "6", "section": "hidrostatica", "problem_id": pid}
    if failure == "missing":
        args["problem_id"] = "PRB-unknown"
    elif failure == "different_step":
        args.update(expression="2+3", result="5")
    elif failure == "different_section":
        dispatch(
            "studium_blueprint_store",
            {"sections": [{"id": "hidrostatica", "title": "One"}, {"id": "other", "title": "Two"}]},
            session=session,
        )
        args["section"] = "other"
    elif failure == "deleted":
        dispatch("studium_problem_remove", {"id": pid}, session=session)
        assert not fold_by_id(root / PROBLEMS)
    elif failure == "source_revoked":
        source = fold_by_id(root / PUBLIC_BIBLIOGRAPHY)[0]
        source["open_supplement"] = False
        append_jsonl(root / PUBLIC_BIBLIOGRAPHY, source)
    elif failure == "invalid_id":
        args["problem_id"] = 123
    result = dispatch("studium_computation_check", args, session=session)
    assert result["accepted"] is False, result
    assert not fold_by_id(root / COMPUTATIONS)
