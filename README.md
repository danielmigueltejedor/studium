<div align="center">

  <img src="docs/assets/studium-logo.png" alt="Studium" width="360">

  <p>
    <strong>Evidence-grounded academic authoring, powered by AI agents.</strong>
  </p>

  <p>
    An open-source framework for researching, writing, verifying, and typesetting academic study books.
  </p>

  <p>
    <a href="https://github.com/danielmigueltejedor/studium/actions/workflows/ci.yml">
      <img src="https://img.shields.io/github/actions/workflow/status/danielmigueltejedor/studium/ci.yml?branch=main&style=flat-square&label=build&logo=githubactions&logoColor=white" alt="Build">
    </a>
    <img src="https://img.shields.io/badge/version-1.0.0a1-64748b?style=flat-square" alt="Version">
    <img src="https://img.shields.io/badge/status-alpha-d97706?style=flat-square" alt="Alpha">
    <img src="https://img.shields.io/badge/Python-3.11+-3776ab?style=flat-square&logo=python&logoColor=white" alt="Python">
    <img src="https://img.shields.io/badge/LaTeX-native-008080?style=flat-square" alt="LaTeX">
    <img src="https://img.shields.io/badge/MCP-compatible-555555?style=flat-square" alt="MCP">
    <a href="./LICENSE">
      <img src="https://img.shields.io/badge/license-Apache--2.0-2563eb?style=flat-square" alt="License">
    </a>
  </p>

  <p>
    <a href="#overview">Overview</a> ·
    <a href="#features">Features</a> ·
    <a href="#how-it-works">How it works</a> ·
    <a href="#getting-started">Getting started</a> ·
    <a href="#architecture">Architecture</a> ·
    <a href="#documentation">Documentation</a>
  </p>

</div>

---

## Overview

**Studium** is an open-source academic authoring framework designed to help AI agents create structured, source-grounded study books.

Instead of treating language models as authorities, Studium separates AI-assisted research and writing from deterministic verification, source tracking, and document generation.

It provides a reproducible workflow for transforming academic sources, university course materials, and research into organized study books with mathematical checks, worked problems, and professional LaTeX typesetting.

Studium is designed for university courses, independent study, and technical subjects, including engineering, mathematics, physics, and computer science.

> [!IMPORTANT]
> **The model is not a source of truth.**
>
> Studium records evidence, checks reproducible results, and tracks the review status of generated content. Automated checks do not constitute academic certification.

### Design principles

- **Evidence first.** Academic claims should be supported by identifiable sources and recorded excerpts.
- **Verification over confidence.** Deterministic checks are preferred over model-generated assurances.
- **Reproducibility.** Projects, sources, checks, and drafts remain available across sessions.
- **Provider independence.** Studium works with external AI clients instead of depending on a specific language model.
- **Transparent limitations.** Unverified content, unresolved contradictions, and incomplete reviews remain explicitly identified.
- **Open architecture.** A Python core, CLI, and MCP interface provide a foundation for integrations and future applications.

## Features

### Academic research

Build a traceable research foundation before generating content.

- University course and independent topic projects
- Public bibliography and source registration
- Source metadata and provenance tracking
- Local document intake
- Source excerpts and citations
- Source versioning and change detection
- Academic blueprint generation
- Research and content coverage reports

Studium distinguishes between source provenance, bibliographic identity, and scientific authority.

User-provided materials can guide the book's organization and terminology without automatically becoming authoritative references.

### Structured book authoring

Generate organized academic content through a persistent authoring workflow.

- Hierarchical chapters and sections
- Academic concepts and learning objectives
- Adaptive depth planning
- Chapter completeness checks
- Definitions and explanatory content
- Worked problems and practice exercises
- Self-assessment sections
- Mathematical derivations
- Notation and terminology management
- Cross-chapter consistency checks

Content is organized around an academic blueprint rather than generated as an unstructured response.

### Mathematical verification

Studium includes deterministic mathematical tools for checking calculations and derivations.

| Capability | Implementation |
|---|---|
| Arithmetic reproduction | Expression evaluation and result comparison |
| Symbolic mathematics | SymPy |
| Dimensional analysis | Pint |
| Numerical cross-checking | Independent numerical substitutions |
| Structured problem checking | Intermediate and final result validation |
| Derivation verification | Combined symbolic, numerical, and dimensional checks |
| Contradiction detection | Stored-content consistency analysis |

Verification results describe the method used.

A reproduced calculation is not automatically a mathematically proven result, and an internally consistent derivation does not establish the validity of its physical assumptions.

### Evidence and quality control

Studium tracks the relationship between academic content and the evidence supporting it.

- Paragraph-level evidence references
- Audits bound to current content revisions
- Stale audit detection
- Numerical claim checks
- Contradiction scanning
- Chapter quality assessment
- Scientific review reports
- Book-wide review records
- Explicit verification states

Changes to source material or authored content can invalidate dependent checks, preventing outdated audit results from being treated as current.

### LaTeX publishing workflow

Transform structured academic content into professionally typeset draft documents.

- Native LaTeX generation
- PDF compilation
- Mathematical notation and equations
- Structured chapters and sections
- Worked-problem and definition environments
- Tables and figures
- Bibliography and source audit
- Formula sheets and notation appendices
- Multilingual document support

Studium currently generates **draft documents**, not officially published or academically certified editions.

## How it works

Studium coordinates academic authoring through a sequence of research, writing, and verification steps.

```text
                    STUDIUM
                       │
                Project creation
                       │
                Source discovery
                       │
             Evidence collection
                       │
               Academic blueprint
                       │
                 Depth planning
                       │
                Chapter authoring
                       │
              ┌────────┴────────┐
              │                 │
        Mathematical       Content and
        verification       source audits
              │                 │
              └────────┬────────┘
                       │
              Contradiction scan
                       │
                 Book review
                       │
                LaTeX rendering
                       │
                   Draft PDF
```

### Agent-driven authoring

Studium exposes its functionality through the **Model Context Protocol (MCP)**.

Compatible AI clients can interact with the framework to create projects, research sources, generate academic content, and request deterministic checks.

The primary orchestration tool is:

`studium_book_next`

It inspects the persisted project state and identifies the next required operation.

This allows an AI client to continue working on an existing book without relying on previous conversation history.

The tool does not autonomously execute the entire workflow. The connected agent must perform the requested operations.

### Quality gates

Before recommending draft rendering, Studium evaluates requirements such as:

- Academic blueprint completeness
- Minimum source coverage
- Sufficient explanatory content
- Required chapter components
- Worked-problem checks
- Current evidence audits
- Unresolved contradictions

Requirements may vary by academic profile.

A chapter that does not satisfy its configured contract remains incomplete.

## Getting started

### Requirements

- Python 3.11 or newer
- Git
- A compatible AI client for agent-assisted authoring
- A LaTeX compiler for PDF generation

Supported PDF compilers include `pdflatex` and `tectonic`.

### Installation

Clone the repository:

```bash
git clone https://github.com/danielmigueltejedor/studium.git
cd studium
```

Create and activate a virtual environment:

```bash
python -m venv venv
source venv/bin/activate
```

Install Studium:

```bash
pip install -e ".[dev]"
```

Verify the installation:

```bash
pytest
```

### Create a project

Studium supports two main project types.

**University course**

```bash
studium create fluidos \
  --course "Mecánica de Fluidos" \
  --university "Universidad de León" \
  --degree "Grado en Ingeniería Aeroespacial"
```

**Independent topic**

```bash
studium create rust --topic "Rust"
```

Course projects retain their academic context, while topic projects do not require university documentation.

### Add source materials

Existing notes, problem sheets, and other supported documents can be registered as project inputs.

```bash
studium sources add ./notes.pdf --project fluidos
```

Imported materials retain their provenance and are not automatically considered scientifically authoritative.

### Connect an AI client

Start the MCP server:

```bash
studium mcp
```

Configure your compatible AI client to launch this command as a local MCP server.

Once connected, the client can access Studium's academic authoring tools.

For HTTP integrations, Studium also provides an MCP endpoint:

```bash
studium mcp --http
```

Remote access is supported through the documented public server configuration with bearer-token authentication.

See the [integration guides](#integrations) for client-specific instructions.

### Generate a draft

Once the project contains the required content and checks:

```bash
studium render --project fluidos
```

Studium writes the LaTeX source to:

```text
latex/draft.tex
```

If a supported compiler is available, it also generates:

```text
latex/draft.pdf
```

Inspect remaining verification blockers with:

```bash
studium verify --full
```

Verification reports the current state of the project. It does not publish or academically certify the book.

## Architecture

Studium is built around a modular Python core.

```text
studium/
├── src/studium/
│   ├── authoring/       # Academic writing and quality control
│   ├── research/        # Sources, excerpts, and research
│   ├── verification/    # Mathematical verification
│   ├── domain/          # Academic models and profiles
│   ├── state/           # Project lifecycle and gates
│   ├── storage/         # Persistence and versioning
│   ├── policy/          # Source and trust policies
│   ├── mcp/             # Model Context Protocol server
│   ├── cli/             # Command-line interface
│   └── config/          # Configuration
├── tests/               # Automated test suite
├── examples/            # Reproducible academic examples
├── integrations/        # AI client integration guides
└── docs/                # Technical documentation
```

### Core components

| Component | Responsibility |
|---|---|
| Research | Source registration, provenance, and evidence collection |
| Authoring | Academic structure, chapters, exercises, and rendering |
| Verification | Mathematical and dimensional checks |
| Quality | Completeness, consistency, and audit reporting |
| State | Project lifecycle and workflow requirements |
| Storage | Persistent records and source versioning |
| MCP | AI-agent interoperability |
| CLI | Local project management |

### AI integration model

Studium does not embed or require a specific AI provider.

Its architecture separates three responsibilities:

1. **AI client:** Performs research and drafting through available capabilities.
2. **Studium core:** Stores academic records and executes deterministic checks.
3. **Document renderer:** Produces structured LaTeX and draft PDFs.

This separation allows the framework to evolve independently of individual models and AI platforms.

## Example project

### Fluid Mechanics — University of León

The repository includes an academic book example for the Aerospace Engineering degree at the University of León.

[Explore the example](./examples/fluid-mechanics-ule)

The example demonstrates:

- A ten-chapter academic blueprint
- Recorded public sources and excerpts
- Worked problems and mathematical derivations
- Numerical and dimensional checks
- Chapter-level audits
- Consistency and quality reports
- LaTeX and PDF generation

The project can be regenerated through its included build script:

```bash
python examples/build-fluid-mechanics-ule.py
```

The example is an independently generated study draft, not official university teaching material.

## Verification model

Studium distinguishes between different levels of mathematical evidence and academic review.

| Status | Meaning |
|---|---|
| `UNVERIFIED` | No conclusive check has been performed |
| `COMPUTATION_REPRODUCED` | A calculation was successfully reproduced |
| `NUMERICALLY_CROSS_CHECKED` | Numerical substitution produced a consistent result |
| `SYMBOLICALLY_VERIFIED` | Symbolic equivalence was checked |
| `DIMENSIONALLY_VERIFIED` | Dimensional consistency was checked |
| `INDEPENDENTLY_VERIFIED` | Multiple distinct verification methods agreed |
| `FAILED` | A check detected an inconsistency or mismatch |
| `ACADEMICALLY_REVIEWED` | Reserved for documented human academic review |

These statuses identify the checks performed, not absolute scientific correctness.

Automatic verification does not replace expert review.

For details, see [Verification Model](./docs/verification-model.md).

Run `studium quality-audit --project /path/to/book` for integrated JSON findings,
or add `--format markdown`. The read-only MCP equivalent is
`studium_book_quality_audit`. Rendering also writes `latex/draft.quality.json`
and `.md` with final-pass compiler diagnostics and record/line mapping.
See [Scientific quality and publishing](./docs/scientific-quality-and-publishing.md)
for contracts, compatibility and explicitly deferred work.

## Project status

Studium is currently in **alpha development**.

The framework implements its core research, authoring, verification, and draft-rendering workflows.

However, it does not yet provide a complete end-user application or a publication system.

| Capability | Status |
|---|---|
| Python core and CLI | Implemented |
| MCP server | Implemented |
| Source and excerpt tracking | Implemented |
| Academic blueprint and depth planning | Implemented |
| Mathematical verification tools | Implemented |
| Evidence audits and contradiction checks | Implemented |
| LaTeX/PDF draft generation | Implemented |
| Desktop application | Planned |
| AI provider management | Available in the [web client](./apps/web/README.md); separate from CLI/MCP |
| Flashcards and study resources | Available in the [web client](./apps/web/README.md), with pending academic review |
| Academic publication workflow | Not implemented |

### Roadmap

Development priorities include:

- Improving source verification and research reliability
- Expanding mathematical and scientific validation
- Strengthening long-running agent workflows
- Improving academic depth and editorial quality
- Increasing real-world evaluation across disciplines
- Building an accessible graphical application
- Supporting additional AI-powered study formats

The browser application in `apps/web` extends the framework with subject libraries, academic book drafts, flashcards, summaries and audio lessons. Native desktop work and further study formats remain on the roadmap.

See [the application proposal](https://github.com/danielmigueltejedor/studium/issues/39) for the proposed scope.

## Integrations

Studium provides integration documentation for different AI environments.

| Client | Guide |
|---|---|
| Claude | [Integration guide](./integrations/claude/README.md) |
| ChatGPT | [Integration guide](./integrations/chatgpt/README.md) |
| Codex | [Integration guide](./integrations/codex/README.md) |
| Cursor | [Integration guide](./integrations/cursor/README.md) |
| Generic MCP clients | [Integration guide](./integrations/generic-mcp/README.md) |

Compatibility depends on each client's MCP capabilities and configuration.

## Documentation

Detailed technical documentation is available in the `docs/` directory.

| Document | Description |
|---|---|
| [Exercises by discipline](./docs/discipline-exercises.md) | Discursive exercises per domain profile and image figures with licences |
| [Research Model](./docs/research-model.md) | Academic research and source discovery |
| [Evidence Model](./docs/evidence-model.md) | Provenance, authority, and source versioning |
| [AI Orchestration](./docs/ai-orchestration.md) | Agent interaction and workflow coordination |
| [Verification Model](./docs/verification-model.md) | Mathematical checks and verification states |
| [Authoring regressions](./docs/turbomachinery-authoring-fixes.md) | Unit powers, equation lead-ins, exercise identity and compatibility |
| [Release Model](./docs/release-model.md) | Review requirements and publication limitations |
| [Security](./docs/security.md) | Source isolation and security boundaries |
| [Copyright](./docs/copyright.md) | Source licensing and copyright considerations |

## Development

Install the development dependencies:

```bash
pip install -e ".[dev]"
```

Run the test suite:

```bash
pytest
```

Check code quality:

```bash
ruff check src tests
```

Run static type analysis:

```bash
pyright
```

Generate a coverage report:

```bash
pytest --cov=studium --cov-report=term-missing
```

Automated checks run through GitHub Actions.

Contributions should include relevant tests and preserve existing verification and provenance guarantees.

See [CONTRIBUTING.md](./CONTRIBUTING.md).

## License

Studium is distributed under the **Apache License 2.0**.

See [LICENSE](./LICENSE).

The software license does not automatically apply to books or content generated using Studium.

Users remain responsible for respecting the rights and license conditions of their source materials.

---

<div align="center">

  <strong>Studium</strong>

  <p>Evidence-grounded academic authoring.</p>

  <p>
    Created and maintained by
    <a href="https://github.com/danielmigueltejedor">Daniel Miguel Tejedor</a>
  </p>

  <p>
    <a href="https://github.com/danielmigueltejedor/studium">Repository</a>
    ·
    <a href="https://github.com/danielmigueltejedor/studium/issues">Issues</a>
    ·
    <a href="https://github.com/danielmigueltejedor/studium/pulls">Contribute</a>
  </p>

</div>

### Explicit scientific claim contracts

Scientific contracts connect an existing claim to equations, units, hypothesis
predicates, derivations and occurrences across theory, examples, self-checks,
problems, solutions and appendices. `studium scientific-contract` records and
reports them; `studium quality-audit` includes their findings in JSON/Markdown.
Checks distinguish algebra, dimensions, singular point values, limits, local
pressure integrability and declared Bernoulli/Stokes hypotheses. Contracts keep
revision fingerprints and reject generated replacements of human corrections.
These are scoped checks of explicit annotations; prose interpretation, physical
applicability and academic approval remain for expert review. See
[the schema, examples and limitations](docs/scientific-contracts.md).

Programming-book literal regions, bounded language adapters, exercise contracts
and explicit evidence-review copies are documented in
[`docs/programming-books.md`](docs/programming-books.md). The additive Python
APIs do not replace the existing mathematical contracts or introduce automatic
academic approval.

## Web application

The Spanish browser client lives in [`apps/web`](apps/web/README.md). It includes
notebooks with ink and original PDF pages, study cards with FSRS, source-sized
podcasts, academic book drafts, calendar planning and an opt-in public community.
The client executes the pinned original Python framework under Pyodide for project
creation, source intake, hierarchy/depth, excerpts, paragraphs and review reports.
It preserves pending academic gates: browser-generated material is a draft, and
TeX compilation and checks that need threads/subprocesses require the native CLI.

Own accounts provide profiles, encrypted provider connections and private library
synchronization. The optional iPad container supplies native Pencil gestures and
account-scoped folder synchronization through Files/iCloud Drive. It still needs
Xcode signing and hardware validation; Safari supports manual Files backups.
See the web README for setup, deployment secrets, storage limits and test evidence.
The graphical desktop roadmap remains separate from this browser client.
