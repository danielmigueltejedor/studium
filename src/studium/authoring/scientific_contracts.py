"""Revision-aware scientific metadata attached to existing claims.

The book and its editorial records are never regenerated here. Each update is
one append under the project lock. Generated proposals cannot replace human
corrections; conflicts are returned as data without changing history.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from studium.authoring.support import citation_context, paragraph_citation_blockers
from studium.storage.locking import ProjectLocked, project_lock
from studium.storage.migrate import utc_now
from studium.storage.records import (
    CLAIMS,
    DERIVATIONS,
    EXCERPTS,
    PARAGRAPHS,
    PROBLEMS,
    PUBLIC_BIBLIOGRAPHY,
    SCIENTIFIC_CONTRACTS,
    append_jsonl,
    fold_by_id,
)
from studium.verification.scientific import assess_contract, validate_contract


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()
    ).hexdigest()


def _records(root: Path) -> dict[str, dict[str, Any]]:
    return {
        str(record["id"]): record
        for path in (CLAIMS, PARAGRAPHS, PROBLEMS, DERIVATIONS, EXCERPTS, PUBLIC_BIBLIOGRAPHY)
        for record in fold_by_id(root / path)
    }


def _dependencies(claim_id: str, contract: dict[str, Any], records: dict[str, dict[str, Any]]) -> dict[str, str]:
    refs = {claim_id, *contract["derivations"], *(entry["record"] for entry in contract["representations"])}
    # Include evidence of every representation, not just the principal claim.
    for identifier in list(refs):
        record = records.get(identifier, {})
        refs.update(record.get("excerpts", []))
        refs.update(record.get("sources", []))
        references = record.get("references", {})
        if isinstance(references, dict):
            for field in ("excerpts", "sources"):
                refs.update(references.get(field, []))
    for identifier in list(refs):
        source = records.get(identifier, {}).get("source_id")
        if isinstance(source, str) and source in records:
            refs.add(source)
    return {identifier: _digest(records.get(identifier)) for identifier in sorted(refs)}


def record_scientific_contract(
    root: Path,
    *,
    claim_id: object,
    contract: object,
    expected_revision: object = None,
    origin: object = "generator",
) -> dict[str, object]:
    """Create/update metadata with optimistic concurrency and editorial ownership."""
    if not isinstance(claim_id, str) or not claim_id or len(claim_id) > 128 or origin not in ("human", "generator"):
        return {"status": "mcp.invalid_input", "message": "claim_id and origin (human or generator) are required"}
    try:
        data = validate_contract(contract)
    except (ValueError, TypeError, RecursionError) as exc:
        return {"status": "mcp.invalid_input", "message": str(exc)}
    try:
        with project_lock(root):
            records = _records(root)
            claims = {item["id"] for item in fold_by_id(root / CLAIMS)}
            if claim_id not in claims:
                return {"status": "claim.not_found", "message": "Attach the contract to an existing claim."}
            anchor_ids = {entry["record"] for entry in data["representations"]}
            known_anchors = {
                item["id"] for path in (CLAIMS, PARAGRAPHS, PROBLEMS, DERIVATIONS) for item in fold_by_id(root / path)
            }
            if anchor_ids - known_anchors:
                return {"status": "scientific.record_missing", "records": sorted(anchor_ids - known_anchors)}
            derivations = {item["id"] for item in fold_by_id(root / DERIVATIONS)}
            if set(data["derivations"]) - derivations:
                return {"status": "scientific.derivation_missing", "message": "Use existing derivation ids."}
            dependencies = _dependencies(claim_id, data, records)
            fingerprint = _digest({"contract": data, "dependencies": dependencies})
            previous = next((item for item in fold_by_id(root / SCIENTIFIC_CONTRACTS) if item["id"] == claim_id), None)
            if previous and previous.get("input_sha256") == fingerprint:
                return {"status": "already_recorded", "contract": previous, "stored_content_modified": False}
            previous_revision = previous.get("revision_sha256") if previous else None
            if expected_revision != previous_revision:
                return {
                    "status": "scientific.revision_conflict",
                    "current_revision": previous_revision,
                    "message": "Read the current revision before reconciling this proposal.",
                    "stored_content_modified": False,
                }
            if previous and origin == "generator" and previous.get("origin") == "human":
                return {
                    "status": "scientific.editorial_conflict",
                    "current_revision": previous_revision,
                    "message": "A generated proposal cannot replace a human correction.",
                    "stored_content_modified": False,
                }
            record: dict[str, object] = {
                "schema_version": "1.0",
                "id": claim_id,
                "contract": data,
                "dependencies": dependencies,
                "input_sha256": fingerprint,
                "previous_revision": previous_revision,
                "origin": origin,
                "revision_sha256": _digest([previous_revision, fingerprint, origin]),
                "recorded_at": utc_now(),
            }
            append_jsonl(root / SCIENTIFIC_CONTRACTS, record)
            return {"status": "recorded", "contract": record, "stored_content_modified": True}
    except ProjectLocked:
        return {"status": "storage.locked", "message": "project is locked"}


def scientific_contract_report(root: Path) -> dict[str, Any]:
    """Recompute current checks. Stale contracts never contribute passing evidence."""
    records = _records(root)
    context = citation_context(root)
    reports = []
    for record in fold_by_id(root / SCIENTIFIC_CONTRACTS):
        claim_id = str(record["id"])
        claim = records.get(claim_id, {})
        base = {"claim": claim_id, "section": claim.get("section"), "revision": record.get("revision_sha256")}
        try:
            data = validate_contract(record.get("contract"))
        except (ValueError, TypeError, RecursionError) as exc:
            reports.append({**base, "state": "invalid", "detail": str(exc)})
            continue
        dependencies = _dependencies(claim_id, data, records)
        fingerprint = _digest({"contract": data, "dependencies": dependencies})
        if record.get("input_sha256") != fingerprint:
            reports.append(
                {
                    **base,
                    "state": "stale",
                    "detail": "A claim, representation, derivation or evidence revision changed.",
                }
            )
            continue
        assessment = assess_contract(data)
        for check in assessment["checks"]:
            check["section"] = records.get(check["record"], {}).get("section")
        excerpts = sorted(set(dependencies) & context.excerpts.keys())
        blockers = paragraph_citation_blockers(root, excerpts, context)
        assessment["verification"]["documentary"] = "EVIDENCE_LOCATED" if not blockers else "UNVERIFIED"
        reports.append(
            {
                **base,
                "state": "current",
                **assessment,
                "evidence": {
                    "excerpts": sorted(excerpts),
                    "blockers": blockers,
                    "semantic_support": "not_established",
                },
            }
        )
    claims = fold_by_id(root / CLAIMS)
    return {
        "status": "ok",
        "advisory": True,
        "stored_content_modified": False,
        "contracts": reports,
        "coverage": {
            "claims": len(claims),
            "annotated_claims": len(reports),
            "current_contracts": sum(item["state"] == "current" for item in reports),
        },
        "scientific_validity": "not_established",
    }
