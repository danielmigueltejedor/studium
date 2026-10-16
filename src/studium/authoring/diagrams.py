"""Diagrams stored as figures, tied to the data and the problem step they explain.

A diagram is an ordinary figure record (TikZ source, caption, excerpts, key)
with a ``diagram`` block:

* ``generator`` and its version, ``settings``;
* ``spec`` (the structured data it was drawn from) and ``spec_sha256``;
* ``problem`` and ``stage`` when it belongs to a step of a problem, and the
  ``structure_sha256`` of that problem's data at generation time;
* ``data``: the solution the drawing shows (exact values as text);
* ``verification``: the checks, apart from the drawing, and their summary.

A diagram whose checks fail is not stored. A diagram whose problem data have
changed since it was drawn is ``stale``: the renderer leaves it out and
:func:`regenerate_diagrams` draws it again from the current data.
"""

import hashlib
import json
from pathlib import Path

from studium.authoring.figures import check_figure, record_figure
from studium.authoring.languages import book_language
from studium.diagrams.evidence import Check, Evidence, summarize
from studium.diagrams.piecewise import DataError
from studium.diagrams.registry import STAGES, Generated, Options, generator, verification_block
from studium.storage.locking import ProjectLocked, project_lock
from studium.storage.migrate import utc_now
from studium.storage.records import FIGURES, PROBLEMS, append_jsonl, fold_by_id

_MAX_SPEC = 60_000
_FAILED_SHOWN = 12


def spec_sha256(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _options(root: Path | None, settings: dict[str, object]) -> Options:
    language = "es"
    if root is not None:
        found = book_language(root)
        if found is not None:
            language = found.tag
    override = settings.get("language")
    if isinstance(override, str) and override.strip():
        language = override.strip()
    decimals = settings.get("decimals")
    return Options(language=language, decimals=decimals if isinstance(decimals, int) and 0 <= decimals <= 6 else 2)


def _settings(value: object) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    if value is None:
        return {}, None
    if not isinstance(value, dict) or len(json.dumps(value, default=str)) > 2_000:
        return None, _error("mcp.invalid_input", "settings must be a small object")
    return dict(value), None


def _spec(value: object) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    if not isinstance(value, dict) or not value:
        return None, _error("mcp.invalid_input", "spec must be an object with the structured data")
    try:
        size = len(json.dumps(value, ensure_ascii=False))
    except (TypeError, ValueError):
        return None, _error("mcp.invalid_input", "spec must be JSON data")
    if size > _MAX_SPEC:
        return None, _error("mcp.invalid_input", "spec is too large")
    return value, None


def run_generator(
    name: object,
    spec: dict[str, object],
    settings: dict[str, object],
    options: Options,
    claims: object = None,
) -> tuple[Generated | None, dict[str, object] | None]:
    """Build one drawing. A data error or an unknown generator is returned, not raised."""

    if not isinstance(name, str):
        return None, _error("mcp.invalid_input", "generator is required")
    found = generator(name)
    if found is None:
        return None, _error("diagram.generator_unknown", f"no generator called {name!r}")
    try:
        return found.build(spec, settings, options, claims), None
    except DataError as exc:
        return None, _error("diagram.data_invalid", str(exc))
    except (ValueError, ZeroDivisionError, TypeError) as exc:
        return None, _error("diagram.data_invalid", f"the data cannot be drawn: {exc}")


def preview_diagram(
    root: Path | None,
    *,
    generator_name: object,
    spec: object,
    settings: object = None,
    claims: object = None,
) -> dict[str, object]:
    """Draw and check without storing. Returns the TikZ, the solution data and the evidence."""

    cleaned, error = _spec(spec)
    if error is not None:
        return error
    options_dict, error = _settings(settings)
    if error is not None:
        return error
    assert cleaned is not None and options_dict is not None
    built, error = run_generator(generator_name, cleaned, options_dict, _options(root, options_dict), claims)
    if error is not None:
        return error
    assert built is not None
    summary = built.evidence.summary()
    return {
        "status": "previewed",
        "stored": False,
        "verification": _verification(built.evidence, summary),
        "data": built.data,
        "tikz": built.tikz,
    }


def _verification(evidence: Evidence, summary: dict[str, object]) -> dict[str, object]:
    return verification_block(evidence, summary)


def problem_structure(root: Path, problem_id: str) -> dict[str, object] | None:
    record = next((item for item in fold_by_id(root / PROBLEMS) if item.get("id") == problem_id), None)
    if record is None:
        return None
    structure = record.get("structure")
    return structure if isinstance(structure, dict) else {}


def record_diagram(
    root: Path,
    *,
    generator_name: object,
    caption: object,
    section: object = None,
    excerpts: object = None,
    key: object = None,
    spec: object = None,
    problem: object = None,
    stage: object = None,
    settings: object = None,
    claims: object = None,
    actor: dict[str, object] | None = None,
) -> dict[str, object]:
    """Generate, check and store one diagram. A diagram whose checks fail is rejected and not stored."""

    found = generator(generator_name) if isinstance(generator_name, str) else None
    if found is None:
        return _error("diagram.generator_unknown", f"no generator called {generator_name!r}")
    options_dict, error = _settings(settings)
    if error is not None:
        return error
    assert options_dict is not None
    problem_id: str | None = None
    structure_sha: str | None = None
    problem_record: dict[str, object] | None = None
    if problem is not None:
        if not isinstance(problem, str) or not problem.strip():
            return _error("mcp.invalid_input", "problem must be a problem id")
        problem_id = problem.strip()
        problem_record = next((item for item in fold_by_id(root / PROBLEMS) if item.get("id") == problem_id), None)
        if problem_record is None:
            return _error("problem.not_found", "no stored problem with that id")
        structure = problem_record.get("structure")
        if not isinstance(structure, dict) or not isinstance(structure.get("spec"), dict):
            return _error("diagram.problem_without_structure", "the problem has no structured data; record it with structure")
        if structure.get("family") != found.family:
            return _error(
                "diagram.family_mismatch",
                f"generator {found.name} draws {found.family} data but the problem holds {structure.get('family')}",
            )
        if spec is not None:
            return _error("mcp.invalid_input", "give spec or problem, not both; a problem diagram is drawn from the problem's data")
        spec = structure["spec"]
        structure_sha = spec_sha256(structure)
        if claims is None:
            claims = structure.get("claims")
        if section is None:
            section = problem_record.get("section")
        if excerpts is None:
            excerpts = problem_record.get("excerpts")
    cleaned, error = _spec(spec)
    if error is not None:
        return error
    assert cleaned is not None
    stage_name: str | None = None
    if stage is not None or problem_id is not None:
        stage_name = stage.strip() if isinstance(stage, str) else (found.stages[0] if found.stages else None)
        if stage_name not in STAGES:
            return _error("mcp.invalid_input", f"stage must be one of {', '.join(STAGES)}")
        if stage_name == "statement" and "statement" not in found.stages:
            return _error(
                "diagram.unsafe_statement",
                f"{found.name} includes derived results and cannot be used in a statement; use a solution stage",
            )
    built, error = run_generator(found.name, cleaned, options_dict, _options(root, options_dict), claims)
    if error is not None:
        return error
    assert built is not None
    summary = built.evidence.summary()
    if summary["status"] == "verification_failed":
        return {
            "status": "rejected",
            "stored": False,
            "message": "The diagram's checks failed, so it was not stored. Fix the data or the claims.",
            "verification": _verification(built.evidence, summary),
        }
    stored = record_figure(
        root,
        section=section,
        caption=caption,
        source=built.tikz,
        kind="tikz",
        excerpts=excerpts,
        key=key,
        actor=actor,
    )
    figure = stored.get("figure")
    if not isinstance(figure, dict) or not isinstance(figure.get("id"), str):
        return stored
    figure_id = str(figure["id"])
    block: dict[str, object] = {
        "generator": found.name,
        "generator_version": found.version,
        "family": found.family,
        "settings": options_dict,
        "spec": cleaned,
        "spec_sha256": spec_sha256(cleaned),
        "data": built.data,
        "verification": _verification(built.evidence, summary),
        "generated_at": utc_now(),
    }
    if claims is not None:
        block["claims"] = claims
    if problem_id is not None:
        block["problem"] = problem_id
        block["structure_sha256"] = structure_sha
    if stage_name is not None:
        block["stage"] = stage_name
    saved = _attach(root, figure_id, block)
    if saved is not None:
        return saved
    checked = check_figure(root, figure_id)
    current = _find(root, figure_id) or {}
    return {
        "status": "recorded",
        "stored": True,
        "figure_id": figure_id,
        "compiled": checked.get("checked") is True,
        "compile_message": None if checked.get("checked") is True else checked.get("message"),
        "verification": block["verification"],
        "diagram": _public_block(current),
        "data": built.data,
    }


def _attach(root: Path, figure_id: str, block: dict[str, object]) -> dict[str, object] | None:
    current = _find(root, figure_id)
    if current is None:
        return _error("figure.not_found", "the figure vanished while it was being stored")
    updated = dict(current)
    updated["diagram"] = block
    try:
        with project_lock(root):
            append_jsonl(root / FIGURES, updated)
    except ProjectLocked:
        return _error("storage.locked", "project is locked")
    return None


def _find(root: Path, figure_id: str) -> dict[str, object] | None:
    return next((item for item in fold_by_id(root / FIGURES) if item.get("id") == figure_id), None)


def diagram_state(root: Path, record: dict[str, object]) -> dict[str, object]:
    """Current verification status of a stored figure.

    Plain figures report ``not_a_diagram``. A diagram tied to a problem is
    ``stale`` when the problem's structured data changed since it was drawn.
    """

    block = record.get("diagram")
    if not isinstance(block, dict):
        return {"status": "not_a_diagram", "stale": False}
    verification = block.get("verification")
    checks = verification.get("checks") if isinstance(verification, dict) else None
    stale_reason = None
    problem_id = block.get("problem")
    if isinstance(problem_id, str):
        structure = problem_structure(root, problem_id)
        if structure is None:
            stale_reason = "the problem was removed"
        elif spec_sha256(structure) != block.get("structure_sha256"):
            stale_reason = "the problem's structured data changed"
    if block.get("stale_reason"):
        stale_reason = str(block["stale_reason"])
    summary = summarize(checks if isinstance(checks, list) else [], stale=stale_reason is not None)
    summary["stale"] = stale_reason is not None
    if stale_reason:
        summary["stale_reason"] = stale_reason
    return summary


def renderable(root: Path, record: dict[str, object]) -> bool:
    """A diagram renders only while its checks pass and its data are current."""

    state = diagram_state(root, record)
    return state["status"] not in ("verification_failed", "stale")


def verify_diagram(root: Path, figure_id: object) -> dict[str, object]:
    """Draw the diagram again from its data and compare.

    ``stale`` when the problem's data changed or the regenerated drawing
    differs from the stored one; otherwise the fresh evidence replaces the
    stored evidence.
    """

    if not isinstance(figure_id, str) or not figure_id.strip():
        return _error("mcp.invalid_input", "id is required")
    record = _find(root, figure_id.strip())
    if record is None:
        return _error("figure.not_found", "no stored figure with that id")
    block = record.get("diagram")
    if not isinstance(block, dict):
        return _error("diagram.not_a_diagram", "that figure was not drawn from structured data")
    state = diagram_state(root, record)
    if state["stale"]:
        return {"status": "stale", "figure_id": record["id"], "verification": state}
    settings = block.get("settings") if isinstance(block.get("settings"), dict) else {}
    assert isinstance(settings, dict)
    spec = block.get("spec")
    assert isinstance(spec, dict)
    built, error = run_generator(block.get("generator"), spec, settings, _options(root, settings), block.get("claims"))
    if error is not None:
        return error
    assert built is not None
    updated_block = dict(block)
    if built.tikz.strip() != str(record.get("source", "")).strip():
        updated_block["stale_reason"] = "the generator now draws something different from the stored drawing"
    updated_block["verification"] = _verification(built.evidence, built.evidence.summary())
    updated_block["verified_at"] = utc_now()
    _preserve_visual(block, updated_block)
    saved = _attach(root, str(record["id"]), updated_block)
    if saved is not None:
        return saved
    current = _find(root, str(record["id"])) or {}
    return {"status": "verified", "figure_id": record["id"], "verification": diagram_state(root, current)}


def _preserve_visual(old: dict[str, object], new: dict[str, object]) -> None:
    """Visual inspections stay attached only while the drawing is unchanged."""

    if new.get("stale_reason"):
        return
    verification = old.get("verification")
    previous = verification.get("checks") if isinstance(verification, dict) else None
    if not isinstance(previous, list):
        return
    visual = [item for item in previous if isinstance(item, dict) and item.get("category") == "visual"]
    if visual:
        fresh = new["verification"]
        assert isinstance(fresh, dict)
        checks = list(fresh.get("checks") or []) + visual
        new["verification"] = {**summarize(checks), "checks": checks}


def regenerate_diagrams(root: Path, *, figure: object = None, problem: object = None) -> dict[str, object]:
    """Redraw diagrams from the current data: one figure, or every diagram of a problem.

    The figure keeps its id, key, caption and stage. A redrawn diagram whose
    checks now fail stays stored but is marked failed and is not rendered.
    """

    targets: list[dict[str, object]] = []
    for record in fold_by_id(root / FIGURES):
        if record.get("deleted") is True:
            continue
        found = record.get("diagram")
        if not isinstance(found, dict):
            continue
        if (isinstance(figure, str) and record.get("id") == figure.strip()) or (
            isinstance(problem, str) and found.get("problem") == problem.strip()
        ):
            targets.append(record)
    if not targets:
        return _error("diagram.not_found", "no diagram matches that figure or problem")
    results = []
    for record in targets:
        raw_block = record.get("diagram")
        assert isinstance(raw_block, dict)
        block: dict[str, object] = dict(raw_block)
        settings = block.get("settings") if isinstance(block.get("settings"), dict) else {}
        assert isinstance(settings, dict)
        spec = block.get("spec")
        claims = block.get("claims")
        structure_sha = block.get("structure_sha256")
        problem_id = block.get("problem")
        if isinstance(problem_id, str):
            structure = problem_structure(root, problem_id)
            if not structure or not isinstance(structure.get("spec"), dict):
                results.append({"figure_id": record["id"], "status": "orphaned", "message": "the problem or its data is gone"})
                continue
            spec = structure["spec"]
            claims = structure.get("claims")
            structure_sha = spec_sha256(structure)
        assert isinstance(spec, dict)
        built, error = run_generator(block.get("generator"), spec, settings, _options(root, settings), claims)
        if error is not None or built is None:
            failed = Evidence()
            failed.add("the current data can be drawn", "symbolic", False, str((error or {}).get("message")))
            block["verification"] = _verification(failed, failed.summary())
            block.pop("stale_reason", None)
            block["structure_sha256"] = structure_sha
            updated = dict(record)
            updated["diagram"] = block
            _store(root, updated)
            results.append({"figure_id": record["id"], "status": "verification_failed", "message": (error or {}).get("message")})
            continue
        block.update(
            {
                "spec": spec,
                "spec_sha256": spec_sha256(spec),
                "data": built.data,
                "verification": _verification(built.evidence, built.evidence.summary()),
                "generated_at": utc_now(),
            }
        )
        current_generator = generator(str(block.get("generator")))
        if current_generator is not None:
            block["generator_version"] = current_generator.version
        if claims is not None:
            block["claims"] = claims
        block["structure_sha256"] = structure_sha
        block.pop("stale_reason", None)
        updated = dict(record)
        updated["source"] = built.tikz
        updated["source_sha256"] = hashlib.sha256(built.tikz.encode("utf-8")).hexdigest()
        updated["diagram"] = block
        updated["status"] = "unchecked"
        updated["correct"] = False
        updated.pop("output", None)
        _store(root, updated)
        compiled = check_figure(root, str(record["id"]))
        results.append(
            {
                "figure_id": record["id"],
                "status": _status_of(block),
                "compiled": compiled.get("checked") is True,
            }
        )
    return {"status": "regenerated", "diagrams": results}


def _status_of(block: dict[str, object]) -> object:
    verification = block.get("verification")
    return verification.get("status") if isinstance(verification, dict) else None


def _store(root: Path, record: dict[str, object]) -> None:
    with project_lock(root):
        append_jsonl(root / FIGURES, record)


def inspect_diagram(
    root: Path,
    figure_id: object,
    *,
    passed: object,
    inspector: object = None,
    notes: object = None,
) -> dict[str, object]:
    """Record that someone looked at the rendered drawing.

    A failed inspection marks the diagram failed. A passed one adds the
    ``visually_inspected`` flag and never upgrades a mathematical status.
    """

    if not isinstance(figure_id, str) or not figure_id.strip():
        return _error("mcp.invalid_input", "id is required")
    if not isinstance(passed, bool):
        return _error("mcp.invalid_input", "passed must be true or false")
    record = _find(root, figure_id.strip())
    if record is None:
        return _error("figure.not_found", "no stored figure with that id")
    block = record.get("diagram")
    who = inspector if inspector in ("human", "agent") else "agent"
    text = notes.strip()[:500] if isinstance(notes, str) else ""
    check = Check(f"visual inspection by {who}", "visual", passed, text).as_dict()
    check["at"] = utc_now()
    if isinstance(block, dict):
        verification = block.get("verification") if isinstance(block.get("verification"), dict) else {}
        assert isinstance(verification, dict)
        previous = verification.get("checks")
        checks = [*(previous if isinstance(previous, list) else []), check]
        new_block = dict(block)
        new_block["verification"] = {**summarize(checks), "checks": checks}
    else:
        new_block = {"generator": None, "verification": {**summarize([check]), "checks": [check]}}
    updated = dict(record)
    updated["diagram"] = new_block
    try:
        _store(root, updated)
    except ProjectLocked:
        return _error("storage.locked", "project is locked")
    return {"status": "inspected", "figure_id": record["id"], "verification": diagram_state(root, updated)}


def statement_placement_issue(record: dict[str, object]) -> str | None:
    """Detect a legacy result-bearing drawing labelled as a statement.

    The generator contract is deterministic; arbitrary captions and custom
    drawings still require human review. Never infer safety from compilation.
    """
    block = record.get("diagram")
    if not isinstance(block, dict) or block.get("stage") != "statement":
        return None
    found = generator(str(block.get("generator")))
    if found is None or "statement" not in found.stages:
        return "The generator has no statement-safe contract; the drawing belongs with the solution."
    return None


def problem_figures(root: Path, problem_id: str) -> list[dict[str, object]]:
    """Live diagrams of one problem, in stage order, then in recording order."""

    found = []
    for index, record in enumerate(fold_by_id(root / FIGURES)):
        if record.get("deleted") is True:
            continue
        block = record.get("diagram")
        if isinstance(block, dict) and block.get("problem") == problem_id:
            # Preserve legacy records and drawings. Only their placement in the
            # draft changes: a result-bearing drawing follows the solution.
            if statement_placement_issue(record):
                record = {**record, "diagram": {**block, "stage": "solution"}}
                block = record["diagram"]
                assert isinstance(block, dict)
            stage = block.get("stage")
            order = STAGES.index(stage) if stage in STAGES else len(STAGES)
            found.append((order, index, record))
    return [record for _, _, record in sorted(found, key=lambda item: (item[0], item[1]))]


def diagram_report(root: Path) -> dict[str, object]:
    """Every diagram with its generator, problem, stage and current verification status."""

    rows = []
    for record in fold_by_id(root / FIGURES):
        if record.get("deleted") is True:
            continue
        block = record.get("diagram")
        if not isinstance(block, dict):
            continue
        state = diagram_state(root, record)
        rows.append(
            {
                "id": record.get("id"),
                "key": record.get("key"),
                "generator": block.get("generator"),
                "problem": block.get("problem"),
                "stage": block.get("stage"),
                "placement_issue": statement_placement_issue(record),
                "compiled": record.get("status") == "checked" and record.get("correct") is True,
                "status": state["status"],
                "flags": state.get("flags"),
                "failed": _names(state.get("failed"))[:_FAILED_SHOWN],
                "stale_reason": state.get("stale_reason"),
            }
        )
    counts: dict[str, int] = {}
    for row in rows:
        counts[str(row["status"])] = counts.get(str(row["status"]), 0) + 1
    return {"status": "ok", "diagrams": rows, "counts": counts}


def _names(value: object) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def _public_block(record: dict[str, object]) -> dict[str, object]:
    block = record.get("diagram")
    if not isinstance(block, dict):
        return {}
    return {key: block.get(key) for key in ("generator", "family", "problem", "stage", "spec_sha256", "structure_sha256")}


def _error(code: str, message: str) -> dict[str, object]:
    return {"status": code, "message": message, "stored": False}
