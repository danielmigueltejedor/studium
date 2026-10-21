"""Explicit local authorizations for repository-owned execution fixtures.

Only fixture tests import this helper. MCP security tests exercise default denial.
"""

from pathlib import Path

from studium.authoring.figures import check_figure
from studium.authoring.problems import check_problem
from studium.storage.records import FIGURES, PROBLEMS, fold_by_id
from studium.verification.execution import ReviewedHostExecution, execution_input_sha256


def checked_figure_fixture(root: Path, identifier: str) -> dict[str, object]:
    record = next(item for item in fold_by_id(root / FIGURES) if item.get("id") == identifier)
    authorization = ReviewedHostExecution(
        execution_input_sha256(str(record["source"]), ["python", "figure"]),
        reviewer="Studium test suite",
        reason="Repository-owned figure fixture, explicitly reviewed for local execution.",
    )
    return check_figure(root, identifier, execution=authorization)


def checked_problem_fixture(root: Path, identifier: str) -> dict[str, object]:
    record = next(item for item in fold_by_id(root / PROBLEMS) if item.get("id") == identifier)
    invocation = record["invocation"]
    assert isinstance(invocation, list)
    authorization = ReviewedHostExecution(
        execution_input_sha256(str(record["source_text"]), [str(item) for item in invocation]),
        reviewer="Studium test suite",
        reason="Repository-owned Rust fixture, explicitly reviewed for local execution.",
    )
    return check_problem(root, identifier, execution=authorization)
