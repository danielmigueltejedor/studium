# Agent instructions

Follow [QUALITY_GATES.md](QUALITY_GATES.md). Never weaken tests or the quality workflow to pass CI without explicit human review. Every behavior change needs regression tests and verifiable execution results.

## Repository-specific deterministic quality contract (2026-10-26)

**Project:** Python/LaTeX publishing and mathematical verification framework.

**Engineering requirements:** Maintain evidence-grade math, dimensional checks, source citations, reproducible PDF compilation and strict fail-closed behavior. Tests require TeX Live.

**Verification commands:** ruff check .; pyright; python -m pytest -q --cov=studium --cov-branch --cov-fail-under=75.

Only report checks as passed when run with actual evidence. Add regression tests for new behavior and boundary/error paths. Never delete/skip/weaken tests, hide failures or reduce thresholds to make CI pass. Require human review for changes to `QUALITY_GATES.md`, `AGENTS.md`, policy and workflows. Make `quality` a required branch status. Missing tooling or pre-existing failures must be disclosed. Preserve the original instructions.
