# Deterministic quality gates

## Non-negotiable AI change contract
- Do not claim tests/builds ran without actual command output.
- Do not skip, delete, weaken, or mock assertions to make the quality gate pass.
- Do not reduce quality thresholds or change CI policies without explicit human review.
- Add tests for changed behavior, edge conditions, and regressions.
- Quality checks are independent evidence, not a guarantee of defect-free behavior.

## Enforced in this repository
- `git diff --check` (patch whitespace).
- `ruff check .` (static errors).
- `pytest --cov=studium --cov-branch --cov-fail-under=75` (tests and minimum coverage).
- Protected branches must require the `quality` check to prevent bypass by direct merging.

## Why 75%?
The existing `pyproject.toml` coverage policy is 75%. Raising it to 85% should be a separately measured change with a new verified baseline, not an arbitrary first-pass CI failure.
