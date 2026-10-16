"""Contracts reuse claim identities, evidence and append-only project storage."""

import json
from copy import deepcopy

import pytest
from test_professional_math import _setup, _structured_solution
from test_quality_audit import _snapshot
from test_scientific_contracts import aerodynamic_contract, contract

from studium.authoring.quality_audit import book_quality_audit
from studium.cli.app import main
from studium.mcp.catalog import _TOOLS, _schema
from studium.mcp.server import dispatch
from studium.storage.locking import project_lock
from studium.storage.records import (
    CLAIMS,
    EXCERPTS,
    PARAGRAPHS,
    PUBLIC_BIBLIOGRAPHY,
    SCIENTIFIC_CONTRACTS,
    append_jsonl,
    fold_by_id,
    read_jsonl,
)


def setup_contract(tmp_path, monkeypatch, origin="generator"):
    session, root, excerpts = _setup(tmp_path, monkeypatch)
    # Synthetic fixture bibliography; this is not a claim about a real course guide.
    for source in fold_by_id(root / PUBLIC_BIBLIOGRAPHY):
        dispatch(
            "studium_public_source_guide_citation", {"id": source["id"], "course_guide_cited": True}, session=session
        )
    claim = dispatch(
        "studium_claim_record",
        {
            "text": "Synthetic maximum-efficiency claim.",
            "excerpts": excerpts,
            "section": "hidrostatica",
        },
        session=session,
    )
    assert claim["status"] == "recorded", claim
    claim_id = claim["claim"]["id"]
    dispatch(
        "studium_blueprint_store",
        {
            "sections": [
                {"id": "hidrostatica", "title": "Synthetic theory chapter"},
                {"id": "aerodinamica", "title": "Synthetic application chapter"},
            ]
        },
        session=session,
    )
    data = aerodynamic_contract()
    for representation in data["representations"]:
        result = dispatch(
            "studium_paragraph_record",
            {
                "section": "hidrostatica" if representation["role"] == "theory" else "aerodinamica",
                "text": "Synthetic " + representation["role"] + " claim.",
                "excerpts": excerpts,
            },
            session=session,
        )
        representation["record"] = result["paragraph"]["id"]
    recorded = dispatch(
        "studium_scientific_contract_record",
        {
            "claim_id": claim_id,
            "contract": data,
            "origin": origin,
        },
        session=session,
    )
    assert recorded["status"] == "recorded", recorded
    return session, root, claim_id, data, recorded["contract"]


def test_book_audit_detects_cross_section_contradiction_and_keeps_pending_sources(tmp_path, monkeypatch):
    session, root, claim_id, _data, _stored = setup_contract(tmp_path, monkeypatch)
    before = _snapshot(root)
    report = book_quality_audit(root)
    failures = [issue for issue in report["issues"] if issue["type"] == "scientific_identity_failed"]
    assert len(failures) == 6
    assert {issue["chapter"] for issue in failures} == {"aerodinamica"}
    assert {issue["evidence"]["role"] for issue in failures} == {
        "derivation",
        "example",
        "self_check",
        "problem",
        "solution",
        "appendix",
    }
    assert all(issue["evidence"]["claim"] == claim_id for issue in failures)
    assert all(issue["severity"] == "ERROR" for issue in failures)
    science = dispatch("studium_scientific_contract_report", {}, session=session)
    assert science["coverage"] == {"claims": 1, "annotated_claims": 1, "current_contracts": 1}
    result = science["contracts"][0]
    assert result["verification"]["documentary"] == "EVIDENCE_LOCATED"
    assert result["evidence"]["semantic_support"] == "not_established"
    assert result["verification"]["expert_review"] == "PENDING"
    assert _snapshot(root) == before
    assert report == book_quality_audit(root)
    assert fold_by_id(root / CLAIMS)[0]["classification"] == "PENDING"


@pytest.mark.parametrize("path", [CLAIMS, PARAGRAPHS, EXCERPTS, PUBLIC_BIBLIOGRAPHY])
def test_changed_dependency_invalidates_contract_instead_of_reusing_its_checks(tmp_path, monkeypatch, path):
    _session, root, _claim_id, _data, _stored = setup_contract(tmp_path, monkeypatch)
    changed = deepcopy(fold_by_id(root / path)[0])
    changed["text"] = "Changed scientific content or source excerpt."
    append_jsonl(root / path, changed)
    report = book_quality_audit(root)
    assert any(issue["type"] == "scientific_contract_stale" for issue in report["issues"])
    assert not any(issue["type"] == "scientific_identity_failed" for issue in report["issues"])
    assert report["scientific_contracts"]["coverage"]["current_contracts"] == 0


def test_two_rebuilds_are_idempotent_and_editorial_overlay_cannot_be_overwritten(tmp_path, monkeypatch):
    session, root, claim_id, generated, stored = setup_contract(tmp_path, monkeypatch)
    original_history = (root / SCIENTIFIC_CONTRACTS).read_bytes()
    # Retrying an identical generated proposal appends nothing, even after a lost response.
    for _ in range(2):
        rebuilt = dispatch(
            "studium_scientific_contract_record",
            {
                "claim_id": claim_id,
                "contract": generated,
                "origin": "generator",
            },
            session=session,
        )
        assert rebuilt["status"] == "already_recorded"
    assert (root / SCIENTIFIC_CONTRACTS).read_bytes() == original_history
    edited = deepcopy(generated)
    edited["bindings"]["cd2"] = "0"
    corrected = dispatch(
        "studium_scientific_contract_record",
        {
            "claim_id": claim_id,
            "contract": edited,
            "origin": "human",
            "expected_revision": stored["revision_sha256"],
        },
        session=session,
    )
    assert corrected["status"] == "recorded"
    revision = corrected["contract"]["revision_sha256"]
    before = _snapshot(root)
    for _ in range(2):
        result = dispatch(
            "studium_scientific_contract_record",
            {
                "claim_id": claim_id,
                "contract": generated,
                "origin": "generator",
                "expected_revision": revision,
            },
            session=session,
        )
        assert result["status"] == "scientific.editorial_conflict"
    assert _snapshot(root) == before
    history = read_jsonl(root / SCIENTIFIC_CONTRACTS)
    assert len(history) == 2 and history[1]["previous_revision"] == history[0]["revision_sha256"]
    assert history[0]["id"] == history[1]["id"] == claim_id
    assert history[1]["contract"] == edited
    report = dispatch("studium_scientific_contract_report", {}, session=session)
    assert all(item["status"] == "SYMBOLICALLY_VERIFIED" for item in report["contracts"][0]["checks"])


def test_stale_writers_missing_records_and_locks_fail_without_changes(tmp_path, monkeypatch):
    session, root, claim_id, data, _stored = setup_contract(tmp_path, monkeypatch)
    edited = deepcopy(data)
    edited["bindings"]["cd2"] = "0"
    before = _snapshot(root)
    result = dispatch("studium_scientific_contract_record", {"claim_id": claim_id, "contract": edited}, session=session)
    assert result["status"] == "scientific.revision_conflict"
    unknown = deepcopy(data)
    unknown["representations"][0]["record"] = "PAR-NONEXISTENT"
    result = dispatch(
        "studium_scientific_contract_record", {"claim_id": claim_id, "contract": unknown}, session=session
    )
    assert result["status"] == "scientific.record_missing"
    with project_lock(root):
        result = dispatch(
            "studium_scientific_contract_record", {"claim_id": claim_id, "contract": edited}, session=session
        )
        assert result["status"] == "storage.locked"
    assert _snapshot(root) == before


def test_generated_revision_can_update_without_erasing_other_book_records(tmp_path, monkeypatch):
    session, root, claim_id, data, stored = setup_contract(tmp_path, monkeypatch)
    before = _snapshot(root)
    data["bindings"]["cd2"] = "0"
    result = dispatch(
        "studium_scientific_contract_record",
        {
            "claim_id": claim_id,
            "contract": data,
            "origin": "generator",
            "expected_revision": stored["revision_sha256"],
        },
        session=session,
    )
    assert result["status"] == "recorded"
    after = _snapshot(root)
    assert {name for name in before if before[name] != after[name]} == {SCIENTIFIC_CONTRACTS}


def test_cli_json_markdown_and_catalog(tmp_path, monkeypatch, capsys):
    _session, root, claim_id, data, _stored = setup_contract(tmp_path, monkeypatch)
    file = tmp_path / "contract.json"
    file.write_text(json.dumps(data))
    assert (
        main(
            [
                "scientific-contract",
                "record",
                "--project",
                str(root),
                "--claim",
                claim_id,
                "--file",
                str(file),
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["status"] == "already_recorded"
    assert main(["scientific-contract", "report", "--project", str(root), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["contracts"][0]["state"] == "current"
    assert main(["quality-audit", "--project", str(root), "--format", "markdown"]) == 0
    markdown = capsys.readouterr().out
    assert "scientific_identity_failed" in markdown and claim_id in markdown
    schemas = {tool["name"]: _schema(tool) for tool in _TOOLS}
    assert schemas["studium_scientific_contract_report"]["annotations"]["class"] == "READ"
    assert schemas["studium_scientific_contract_record"]["inputSchema"]["required"] == ["claim_id", "contract"]
    file.write_text("not JSON")
    assert (
        main(["scientific-contract", "record", "--project", str(root), "--claim", claim_id, "--file", str(file)]) != 0
    )


def test_invalid_contract_record_is_reported_without_trusting_its_result(tmp_path, monkeypatch):
    _session, root, _claim_id, _data, stored = setup_contract(tmp_path, monkeypatch)
    record = deepcopy(stored)
    record["contract"]["unsupported_automatic_truth"] = True
    append_jsonl(root / SCIENTIFIC_CONTRACTS, record)
    report = book_quality_audit(root)
    assert any(issue["type"] == "scientific_contract_invalid" for issue in report["issues"])
    assert not any(issue["type"] == "scientific_identity_failed" for issue in report["issues"])


def test_unannotated_book_is_explicitly_outside_contract_coverage(tmp_path, monkeypatch):
    _, root, _ = _setup(tmp_path, monkeypatch)
    report = book_quality_audit(root)
    assert report["scientific_contracts"]["coverage"]["current_contracts"] == 0
    assert "unannotated" in " ".join(report["limitations"])


def test_missing_hypothesis_is_review_not_demonstrated_error(tmp_path, monkeypatch):
    session, root, claim_id, data, stored = setup_contract(tmp_path, monkeypatch)
    data = contract([{"kind": "model", "model": "steady_stokes"}])
    data["representations"][0]["record"] = claim_id
    result = dispatch(
        "studium_scientific_contract_record",
        {
            "claim_id": claim_id,
            "contract": data,
            "expected_revision": stored["revision_sha256"],
            "origin": "human",
        },
        session=session,
    )
    assert result["status"] == "recorded"
    findings = book_quality_audit(root)["issues"]
    missing = next(item for item in findings if item["type"] == "scientific_model_undecided")
    assert missing["severity"] == "REVIEW_REQUIRED"


def test_existing_problem_and_derivation_ids_and_evidence_are_bound(tmp_path, monkeypatch):
    session, root, claim_id, _data, stored = setup_contract(tmp_path, monkeypatch)
    excerpts = fold_by_id(root / CLAIMS)[0]["excerpts"]
    problem = dispatch(
        "studium_problem_record",
        {
            "section": "hidrostatica",
            "prompt": "Synthetic pressure calculation.",
            "expected": "97903.8",
            "excerpts": excerpts,
            "solution": _structured_solution(),
            "role": "worked",
        },
        session=session,
    )
    assert problem["status"] == "recorded", problem
    derivation = dispatch(
        "studium_derivation_record",
        {
            "section": "hidrostatica",
            "name": "Synthetic identity",
            "equation": "x=x",
            "references": {"excerpts": excerpts},
        },
        session=session,
    )
    assert derivation["status"] == "recorded", derivation
    derivation_id = derivation["derivation"]["id"]
    data = contract([{"kind": "identity", "left": "x", "right": "x"}])
    data["representations"][0].update(record=problem["problem"]["id"], role="solution")
    data["representations"].append(
        {
            "record": derivation_id,
            "role": "derivation",
            "requires": [],
            "checks": [{"kind": "identity", "left": "x", "right": "x"}],
        }
    )
    data["derivations"] = [derivation_id]
    result = dispatch(
        "studium_scientific_contract_record",
        {
            "claim_id": claim_id,
            "contract": data,
            "expected_revision": stored["revision_sha256"],
        },
        session=session,
    )
    assert result["status"] == "recorded", result
    assert derivation_id in result["contract"]["dependencies"]
    report = dispatch("studium_scientific_contract_report", {}, session=session)
    assert set(report["contracts"][0]["evidence"]["excerpts"]) == set(excerpts)
    assert {check["role"] for check in report["contracts"][0]["checks"]} == {"solution", "derivation"}
