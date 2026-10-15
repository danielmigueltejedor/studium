# Copilot review guidance — Studium

Studium is an evidence-grounded, fail-closed academic-book authoring framework, not an automatic truth verifier or publisher. Read `README.md`, `docs/evidence-model.md`, `docs/verification-model.md`, and affected tests before reviewing. Focus on actual regressions and actionable findings introduced by the PR.

- **Evidence provenance:** prevent fabricated source URLs, excerpts, citations, or tool results. Recorded web sources must represent pages the client actually opened; user-supplied files are inputs, not independent academic authority.
- **Fail-closed verification:** never allow missing, contradictory, stale, or unverified evidence to silently pass gates. Changes to paragraph/excerpt text must invalidate dependent audits. Keep blockers explicit.
- **Honest status claims:** `audit_passed` is not publication or proof of academic correctness. Computation replay, two agreeing excerpts, and repeated Rust runs have their documented limited meanings. Never label drafts as released or mathematically verified without justified evidence.
- **Mathematics and rendering:** flag dimensional inconsistency, invalid assumptions, symbolic/numeric edge cases, incorrect units, and LaTeX escaping/structure errors. Ask for reproducible checks instead of trusting model output.
- **State and security:** preserve persisted workflow state across sessions, validate external inputs and paths, and avoid leaking private notes, credentials, or copyrighted course content into tests or repository fixtures.
- **Interfaces and tests:** preserve documented CLI and MCP contracts. Request regressions for new failure paths, stale audits, missing evidence, contradictions, and math boundary cases. Respect Python 3.11+, Ruff, Pyright, pytest and the coverage gate in `pyproject.toml`.
- **PR description:** identify missing or unsupported testing/evidence claims in the overall review; structural requirements are enforced separately.

Explain the exact failure mode and suggest the smallest correction. Do not assert that CI ran or that any result was academically proved unless the PR supplies verifiable evidence. Avoid purely stylistic or speculative comments.
