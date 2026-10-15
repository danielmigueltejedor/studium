# Contributing to Studium

Studium builds **draft** academic books from traceable evidence. The AI model is not an authority; a passing audit or reproduced computation is not proof of correctness or publication. Read `README.md`, `docs/evidence-model.md`, and `docs/verification-model.md` before changing verification semantics.

## Submit a focused pull request

Use the pull request template. Explain the behavior before/after, motivation, tests you ran, compatibility implications, and any impact on provenance, audit invalidation, or verification. Link a relevant issue when one exists. Keep the change focused and add regression tests for observable behavior and failure paths.

Never add private student/course files, credentials, unlicensed books, or copied source material as fixtures. External URLs and quotations must not be invented.

## Development checks

Requires Python 3.11 or newer:

```bash
python -m pip install -e ".[dev]"
ruff check src tests
pyright
python -m pytest -q --cov=studium --cov-report=term-missing
```

The current coverage gate is defined in `pyproject.toml` (75% overall minimum). CI tests Python 3.11 and 3.12, installs LaTeX, and runs the commands above. Test rendering changes with a LaTeX compiler when relevant; describe any skipped manual check.

## Review expectations

Preserve documented CLI and MCP contracts, persisted state, provenance, distinction between drafts and releases, and fail-closed behavior when sources or checks are missing. A change that loosens a gate must include a precise justification and tests proving unsupported content remains blocked.
