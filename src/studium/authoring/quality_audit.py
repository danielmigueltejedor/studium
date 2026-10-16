"""Read-only, integrated quality findings from existing deterministic checks.

This report never promotes a record or treats citation diversity as scientific
corroboration. Findings name their method and separate failure from uncertainty.
"""

import hashlib
import json
import re
from collections.abc import Callable
from pathlib import Path

from studium.authoring.audit import audited_paragraph_ids
from studium.authoring.contradictions import open_contradictions
from studium.authoring.diagrams import diagram_state, statement_placement_issue
from studium.authoring.excerpts import excerpts_by_id
from studium.authoring.figures import unresolved_figure_references
from studium.authoring.grounding import GroundingContext, equation_evidence
from studium.authoring.problem_review import review_stored_problem
from studium.authoring.problems import problem_result_current
from studium.authoring.scientific_contracts import scientific_contract_report
from studium.authoring.support import paragraph_citation_blockers
from studium.storage.records import FIGURES, PARAGRAPHS, PROBLEMS, fold_by_id

AddFinding = Callable[[dict[str, object], str, str, object, str, str], None]


def solution_gaps(solution: dict[str, object]) -> list[str]:
    """Structural completeness, independent of answer length or scientific truth."""
    missing = [
        key for key in ("given", "unknown", "model", "assumptions", "result", "interpretation") if not solution.get(key)
    ]
    steps = solution.get("steps")
    records = [step for step in steps if isinstance(step, dict)] if isinstance(steps, list) else []
    if not records and not solution.get("development"):
        missing.append("development")
    if any(not step.get("text") for step in records):
        missing.append("step_explanations")
    if records and not any(step.get("equation") or step.get("symbolic") for step in records):
        missing.append("symbolic_steps")
    if any(step.get("expression") and not step.get("unit") for step in records):
        missing.append("step_units")
    result = solution.get("result")
    final_unit = records[-1].get("unit") if records else None
    if (
        isinstance(result, str)
        and re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", result.strip())
        and isinstance(final_unit, str)
        and final_unit.strip().lower() not in ("1", "dimensionless", "adimensional")
    ):
        missing.append("result_units")
    return missing


def book_quality_audit(root: Path) -> dict[str, object]:
    """Build JSON-compatible findings without writing project records or checks."""
    issues: list[dict[str, object]] = []

    def add(
        record: dict[str, object], kind: str, severity: str, evidence: object, method: str, suggestion: str
    ) -> None:
        identity = json.dumps([record.get("id"), kind, evidence], sort_keys=True, ensure_ascii=True)
        issues.append(
            {
                "id": "QUAL-" + hashlib.sha256(identity.encode()).hexdigest()[:12],
                "severity": severity,
                "chapter": record.get("section"),
                "record": record.get("id"),
                "type": kind,
                "evidence": evidence,
                "method": method,
                "suggestion": suggestion,
                "verification": "detected" if severity == "ERROR" else "requires_review",
            }
        )

    _audit_paragraphs(root, add)
    _audit_problems(root, add)
    _audit_figures(root, add)
    _audit_editorial(root, issues, add)
    science = scientific_contract_report(root)
    for contract in science["contracts"]:
        record = {"id": contract["claim"], "section": contract["section"]}
        if contract["state"] != "current":
            add(record, "scientific_contract_" + contract["state"], "WARNING", contract, "revision_fingerprint",
                "Reconcile the contract with the current records before relying on its checks.")
            continue
        for check in contract["checks"]:
            if check["status"] in ("FAILED", "UNVERIFIED"):
                anchor = {"id": check["record"], "section": check["section"]}
                add(anchor, "scientific_" + check["kind"] + ("_failed" if check["status"] == "FAILED" else "_undecided"),
                    "ERROR" if check["status"] == "FAILED" else "REVIEW_REQUIRED",
                    {"claim": contract["claim"], **check}, "explicit_scientific_contract",
                    "Review the declared equation and its hypotheses across the linked book representations.")
        add(record, "scientific_scope_review", "REVIEW_REQUIRED", contract, "explicit_scientific_contract",
            "Review correspondence to prose, physical applicability and semantic source support; individual checks have limited scopes.")
    return {
        "status": "ok",
        "schema_version": "1.0",
        "advisory": True,
        "stored_content_modified": False,
        "scientific_validity": "not_established",
        "issues": issues,
        "scientific_contracts": science,
        "counts": {
            level: sum(item["severity"] == level for item in issues)
            for level in ("ERROR", "WARNING", "REVIEW_REQUIRED", "INFO")
        },
        "limitations": [
            "Arbitrary prose claims, model applicability and source independence require expert review.",
            "Scientific contracts check explicit annotations; unannotated book content has no inferred scientific clearance.",
            "Structural completeness is not a pedagogical or scientific quality score.",
            "Editorial reports bind to TeX bytes, not to later changes in unrendered book records.",
        ],
    }


def _audit_paragraphs(root: Path, add: AddFinding) -> None:
    excerpts = excerpts_by_id(root)
    audited = audited_paragraph_ids(root)
    context = GroundingContext(root)
    for record in fold_by_id(root / PARAGRAPHS):
        refs = record.get("excerpts")
        refs = [ref for ref in refs if isinstance(ref, str)] if isinstance(refs, list) else []
        absent = [ref for ref in refs if ref not in excerpts]
        if absent:
            add(
                record,
                "missing_excerpt",
                "ERROR",
                absent,
                "record_lookup",
                "Restore or replace the missing evidence link.",
            )
        blockers = paragraph_citation_blockers(root, refs)
        if blockers:
            add(
                record,
                "citation_blocked",
                "WARNING",
                blockers,
                "citation_policy",
                "Resolve citation policy blockers; the paragraph may be excluded from the draft.",
            )
        if record.get("id") not in audited:
            add(
                record,
                "audit_missing_or_stale",
                "WARNING",
                "No current evidence audit.",
                "audit_fingerprint",
                "Audit the current paragraph and evidence revision.",
            )
        for equation in equation_evidence(root, record, context):
            status = equation["status"]
            if status in ("contradicted", "verification_failed"):
                add(
                    record,
                    "equation_check_failed",
                    "ERROR",
                    equation,
                    "equation_evidence",
                    "Inspect the demonstrated mathematical inconsistency.",
                )
            elif equation.get("blocks_audit") or equation.get("human_review") in ("required", "recommended"):
                add(
                    record,
                    "equation_review",
                    "REVIEW_REQUIRED",
                    equation,
                    "equation_evidence",
                    "Review this exact claim against its hypotheses and cited excerpt.",
                )



def _audit_problems(root: Path, add: AddFinding) -> None:
    for record in fold_by_id(root / PROBLEMS):
        current = problem_result_current(root, record)
        kind = record.get("kind")
        status = record.get("status")
        numeric_check_present = kind != "numeric" or isinstance(record.get("answer_check"), dict)
        checked_status = status == ("checked" if kind == "rust" else "two_witnesses")
        if not current or not checked_status or not numeric_check_present:
            add(
                record,
                "problem_unchecked_or_stale",
                "WARNING",
                {
                    "status": status,
                    "fingerprint_current": current,
                    "numeric_check_present": numeric_check_present,
                },
                "problem_result_state",
                "Check this current problem revision before relying on its stored result.",
            )
        if kind != "numeric":
            continue
        refs = record.get("excerpts")
        refs = [ref for ref in refs if isinstance(ref, str)] if isinstance(refs, list) else []
        blockers = paragraph_citation_blockers(root, refs)
        if blockers:
            add(
                record,
                "problem_citation_blocked",
                "WARNING",
                blockers,
                "citation_policy",
                "Resolve the citation policy blockers before relying on this problem's evidence.",
            )
        solution = record.get("solution")
        solution = solution if isinstance(solution, dict) else {}
        gaps = solution_gaps(solution)
        if gaps:
            add(
                record,
                "solution_incomplete",
                "WARNING",
                gaps,
                "structured_solution_contract",
                "Supply the missing pedagogical fields; do not invent intermediate equations.",
            )
        review = review_stored_problem(root, problem_id=record.get("id"))
        report = review.get("report")
        outputs = report.get("outputs") if isinstance(report, dict) else None
        checks = outputs.get("checks") if isinstance(outputs, dict) else None
        if isinstance(checks, dict):
            for name in ("dimensional", "numeric"):
                check = checks.get(name)
                if isinstance(check, dict) and check.get("status") == "FAILED":
                    add(
                        record,
                        name + "_check_failed",
                        "ERROR",
                        check,
                        str(check.get("method")),
                        "Correct the model, data or units and rerun the check.",
                    )
        arithmetic = record.get("answer_check")
        if current and isinstance(arithmetic, dict) and arithmetic.get("result") == "mismatch":
            add(
                record,
                "answer_mismatch",
                "ERROR",
                arithmetic,
                "arithmetic_replay",
                "Reconcile the stated answer with the final replayed step.",
            )
        step_checks = record.get("step_checks")
        if current and isinstance(step_checks, list):
            for check in step_checks:
                if not isinstance(check, dict) or check.get("reproduced") is not False:
                    continue
                ambiguous = check.get("precision") == "ambiguous"
                add(
                    record,
                    "step_check_failed",
                    "WARNING" if ambiguous else "ERROR",
                    check,
                    "arithmetic_replay",
                    (
                        "Clarify the written precision and rerun the check."
                        if ambiguous
                        else "Correct the step's expected value or expression and rerun the check."
                    ),
                )
        add(
            record,
            "scientific_review_required",
            "REVIEW_REQUIRED",
            review.get("evidence", {}),
            "structured_problem_scientific_review",
            "Review model applicability, assumptions and conclusions with an expert; reproduced arithmetic is insufficient.",
        )
        add(
            record,
            "claim_support_unestablished",
            "REVIEW_REQUIRED",
            {
                "excerpts": record.get("excerpts"),
                "source_diversity": record.get("status") == "two_witnesses",
                "semantic_support": "not_established",
            },
            "evidence_scope",
            "Check whether each cited excerpt supports this exact claim under the same hypotheses; distinct documents alone do not corroborate it.",
        )



def _audit_figures(root: Path, add: AddFinding) -> None:
    for record in fold_by_id(root / FIGURES):
        issue = statement_placement_issue(record)
        if issue:
            add(
                record,
                "statement_diagram_leak",
                "ERROR",
                issue,
                "generator_stage_contract",
                "Record this result-bearing drawing at a solution stage. Legacy drafts place it with the solution.",
            )
        state = diagram_state(root, record)
        if state.get("status") in ("verification_failed", "stale"):
            add(
                record,
                "diagram_" + str(state["status"]),
                "WARNING",
                state,
                "diagram_evidence",
                "Regenerate and inspect the diagram against the current problem data.",
            )
        if record.get("status") != "checked" or record.get("correct") is not True:
            add(
                record,
                "figure_unchecked",
                "WARNING",
                record.get("status"),
                "figure_compile_status",
                "Compile and visually inspect this figure.",
            )
    for ref in unresolved_figure_references(root):
        add(
            {},
            "unresolved_figure",
            "WARNING",
            ref,
            "figure_reference_lookup",
            "Record and check the referenced figure.",
        )
    for contradiction in open_contradictions(root):
        add(
            contradiction,
            "open_contradiction",
            "REVIEW_REQUIRED",
            contradiction,
            "stored_contradiction",
            "Review and resolve the conflicting records.",
        )



def _audit_editorial(root: Path, issues: list[dict[str, object]], add: AddFinding) -> None:
    editorial = root / "latex" / "draft.quality.json"
    if editorial.is_file():
        try:
            report = json.loads(editorial.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            add({}, "editorial_report_unreadable", "WARNING", str(exc), "report_load", "Render the draft again.")
        else:
            tex = root / "latex" / "draft.tex"
            digest = hashlib.sha256(tex.read_bytes()).hexdigest() if tex.is_file() else None
            if isinstance(report, dict) and report.get("document_sha256") == digest:
                stored_issues = report.get("issues")
                if isinstance(stored_issues, list) and all(
                    isinstance(item, dict) and item.get("severity") in ("ERROR", "WARNING", "INFO")
                    for item in stored_issues
                ):
                    issues.extend(stored_issues)
                    if report.get("compiled") is False and report.get("compiler") is None:
                        add(
                            {},
                            "editorial_not_compiled",
                            "WARNING",
                            "No LaTeX compiler was available.",
                            "compiler_availability",
                            "Install a supported compiler and render the draft before assessing PDF quality.",
                        )
                else:
                    add(
                        {},
                        "editorial_report_unreadable",
                        "WARNING",
                        "Invalid issue schema.",
                        "report_load",
                        "Render the draft again.",
                    )
            else:
                add(
                    {},
                    "editorial_report_stale",
                    "WARNING",
                    "The report does not match the current TeX.",
                    "document_fingerprint",
                    "Render the draft again before using its editorial report.",
                )
    else:
        add(
            {},
            "editorial_not_checked",
            "INFO",
            "No compiler report exists.",
            "report_lookup",
            "Render a draft and inspect its PDF and final-pass compiler report.",
        )
