<div align="center">
  <img src="docs/assets/studium-logo.png" alt="Studium" width="420">

  <p><strong>Build rigorous, evidence-grounded university textbooks with AI.</strong></p>

  <p>
    <a href="https://github.com/danielmigueltejedor/studium/actions">
      <img src="https://img.shields.io/github/actions/workflow/status/danielmigueltejedor/studium/ci.yml?branch=main&label=CI&logo=github" alt="CI">
    </a>
    <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white" alt="Python 3.11+">
    <img src="https://img.shields.io/badge/LaTeX-native-008080?logo=latex&logoColor=white" alt="LaTeX">
    <img src="https://img.shields.io/badge/AI-provider%20agnostic-6C63FF" alt="AI provider agnostic">
    <a href="./LICENSE">
      <img src="https://img.shields.io/badge/license-Apache--2.0-2EA44F" alt="Apache License 2.0">
    </a>
    <img src="https://img.shields.io/badge/status-active%20development-orange" alt="Active development">
  </p>

  <p>
    <a href="#quick-start">Quick start</a> ·
    <a href="#how-studium-works">How it works</a> ·
    <a href="#verification">Verification</a> ·
    <a href="#architecture">Architecture</a> ·
    <a href="#documentation">Documentation</a> ·
    <a href="#contributing">Contributing</a>
  </p>
</div>

---

**Studium** is an open-source, AI-native framework for turning a real university course into a structured, evidence-grounded and professionally typeset academic textbook.

Give Studium a **course, university and degree**. It provides the research, provenance, verification, authoring and publishing workflow required for a modern AI agent to discover the official syllabus, find authoritative academic sources, build a coherent body of knowledge, create original explanations and exercises, verify critical content, and produce a polished LaTeX book.

```bash
studium create fluid-mechanics \
  --course "Mecánica de Fluidos" \
  --university "Universidad de León" \
  --degree "Grado en Ingeniería Aeroespacial"

studium run
```

Studium works from only a course, university, and degree. If you have lecture notes, Moodle material, exams, or problem sheets, you can provide them to align the result with your real course. Local sources are optional. When available, they can improve course alignment. They are never assumed to be authoritative simply because they were provided.

> [!IMPORTANT]
> **Studium does not treat AI-generated text as evidence.**
>
> AI is used to research, compare, derive, verify, explain and organize information from traceable sources. High-risk academic claims are not considered verified merely because a language model produced them.

## Why Studium?

Most AI study workflows currently look like this:

```text
prompt
  ↓
plausible-looking notes
  ↓
PDF
```

Studium is designed around a different model:

```text
Course
  ↓
Official curriculum discovery
  ↓
Academic research
  ↓
Sources + provenance
  ↓
Claims + evidence
  ↓
Knowledge graph
  ↓
Authoring
  ↓
Verification
  ↓
Independent review
  ↓
LaTeX
  ↓
Release
```

The goal is not simply to generate more text.

The goal is to make AI-generated academic material **inspectable, reproducible and substantially harder to get wrong**.

## Quick start

### 1. Install Studium

Clone the repository and install the development package:

```bash
git clone https://github.com/danielmigueltejedor/studium.git
cd studium

python -m venv venv
source venv/bin/activate

pip install -e .
```

Name that environment `venv`. On macOS, iCloud Drive (Desktop and Documents included) sets the hidden flag on everything inside a dot-directory such as `.venv`. Python skips hidden `.pth` files, so the editable install never adds `src` to `sys.path`. The `studium` command then fails with `ModuleNotFoundError: No module named 'studium'`. The first run can succeed, and the next one fails after iCloud flags the new path file. A regular `pip install .` copies the package into `site-packages` and does not use that file.

Check the environment:

```bash
studium doctor
```

### 2. Create a course

Only three pieces of information are required:

```bash
studium create fluid-mechanics \
  --course "Mecánica de Fluidos" \
  --university "Universidad de León" \
  --degree "Grado en Ingeniería Aeroespacial"
```

Studium creates an academic project and determines the next required stage.

```bash
studium status
studium next
```

### 3. Let an AI agent work through Studium

Generate the context required for the current task:

```bash
studium agent-pack
```

Or let a compatible coding/research agent follow Studium's orchestration protocol:

```bash
studium run
```

Studium is designed to remain **AI-provider agnostic**. The academic workflow lives in Studium rather than in a specific model or vendor.

### 4. Verify and build

```bash
studium verify --full
studium build
```

When every mandatory gate passes:

```bash
studium release
```

## Bring your own sources

Studium does not require local source material.

If all you know is:

```text
Course
University
Degree
```

the research workflow starts by finding and validating the official course information and then building an academic corpus from suitable external sources.

If you also have course material:

```text
sources/
├── lecture-notes.pdf
├── slides.pdf
├── problem-sheet.pdf
├── exam-2025.pdf
└── formula-sheet.pdf
```

you can include it during project creation:

```bash
studium create fluid-mechanics \
  --course "Mecánica de Fluidos" \
  --university "Universidad de León" \
  --degree "Grado en Ingeniería Aeroespacial" \
  --sources ~/Documents/FluidMechanics
```

Local material is treated as **input to be audited**, not automatically as truth.

Studium does not automatically commit or upload private course files.

## How Studium works

Studium models a textbook as an **Academic Knowledge Project**, not merely a collection of `.tex` files.

```text
┌──────────────────────────────┐
│            Course            │
│ syllabus · outcomes · exams  │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│           Research           │
│ books · papers · standards   │
│ universities · primary data  │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│      Evidence & Knowledge    │
│ sources · claims · concepts  │
│ equations · derivations      │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│          Authoring           │
│ chapters · figures · worked  │
│ examples · original problems │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│        Verification          │
│ evidence · math · units      │
│ citations · exercises        │
│ consistency · red team       │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│           Release            │
│ LaTeX · PDF · lockfile       │
│ verification certificate     │
└──────────────────────────────┘
```

### Course discovery

Studium instructs the research agent to identify and verify, whenever available:

- the official course page and teaching guide;
- institution and degree;
- current academic year;
- course code;
- ECTS/credits;
- semester and prerequisites;
- learning outcomes and competencies;
- official syllabus;
- assessment structure;
- recommended bibliography.

A matching course name alone is not considered sufficient identification.

### Academic research

Different questions require different sources.

Studium encourages agents to prefer:

| Need | Preferred evidence |
|---|---|
| Course scope | Official university documentation |
| Established theory | Academic textbooks and university material |
| Current research | Peer-reviewed reviews and primary literature |
| Standards and regulations | Official standards or issuing bodies |
| Numerical data | Primary datasets or responsible institutions |
| Historical claims | Primary sources and academic historiography |
| Software behaviour | Primary documentation, standards and source code |

Search results and snippets are discovery mechanisms, **not evidence**.

## Evidence model

Studium tracks important academic entities using stable identifiers.

```text
SRC-*   Source
CLM-*   Claim
CON-*   Concept
EQ-*    Equation
DER-*   Derivation
FIG-*   Figure
EX-*    Exercise
CH-*    Chapter
REV-*   Review
```

Relationships form an academic evidence graph:

```text
SRC-WHITE-001
      │
      └── supports ──▶ CLM-FM-042
                            │
                            └── assumed by ──▶ DER-FM-011
                                                   │
                                                   └── derives ──▶ EQ-FM-018
                                                                      │
                                            ┌─────────────────────────┴─────────────┐
                                            ▼                                       ▼
                                      EX-FM-032                              FIG-FM-014
```

This enables impact analysis.

If a critical derivation changes, dependent equations, exercises, figures and reviews can be marked stale instead of silently retaining an old `PASS`.

```bash
studium graph --entity DER-FM-011
studium graph --impact DER-FM-011
```

## Verification

Studium follows a fail-closed philosophy for critical academic content.

```text
NO EVIDENCE
    → NO HIGH-RISK VERIFIED CLAIM

PHYSICAL EQUATION
    → CHECK DIMENSIONS

IMPORTANT DERIVATION
    → INDEPENDENT REVIEW

SOLVED EXERCISE
    → INDEPENDENT SOLUTION

COMPUTABLE RESULT
    → COMPUTATIONAL VERIFICATION WHEN APPLICABLE

CONTENT CHANGED
    → DEPENDENT REVIEWS BECOME STALE

UNRESOLVED BLOCKER
    → NO RELEASE
```

### Claims and citations

Studium distinguishes between a citation being present and a citation actually supporting a statement.

Support can be classified as:

```text
DIRECT_SUPPORT
PARTIAL_SUPPORT
BACKGROUND
DERIVATION_INPUT
CONTRADICTS
DOES_NOT_SUPPORT
```

A high-risk claim cannot pass a release gate with inadequate evidence.

### Mathematics and physics

For applicable disciplines, Studium can track and verify:

- assumptions;
- symbolic derivations;
- algebraic equivalence;
- derivatives and integrals;
- dimensions and units;
- boundary conditions;
- limiting cases;
- numerical results;
- physical consistency.

Computational verification can use tools such as Python and SymPy where useful.

### Exercises as testable academic content

Studium treats worked problems as material that deserves verification rather than filler generated after the theory.

A relevant solved exercise can require:

```text
Author solution
      +
Independent solution
      +
Unit and dimension checks
      +
Symbolic or numerical verification
      +
Academic review
```

Exercise material derived from previous exams should reproduce **skills and difficulty**, not protected wording.

### Beyond STEM

Studium's verification model is designed to support multiple academic domains.

Examples include:

| Domain | Verification focus |
|---|---|
| STEM | Mathematics, dimensions, derivations, numerical checks |
| Humanities | Primary sources, attribution, chronology, interpretation |
| Social sciences | Methods, samples, statistics, causal claims |
| Law | Jurisdiction, legal source, version and date of applicability |
| Computer science | Standards, primary documentation, executable tests |

Domain-specific verification extends a common evidence and provenance core.

## Designed for study

Studium is not intended to produce generic reference encyclopedias by default.

A course book can combine:

- rigorous theory;
- intuitive explanations;
- step-by-step derivations;
- worked examples;
- original exercises;
- applications;
- common mistakes;
- chapter summaries;
- exam-oriented practice;
- cross-references;
- terminology and symbol registries.

The official curriculum defines **what must be covered**.

Studium is free to find a better pedagogical order for explaining it.

## AI-provider agnostic

Studium is designed around protocols and durable repository artifacts rather than one model provider.

Compatible agent workflows may be built around tools such as:

- Cursor;
- OpenAI Codex;
- Claude Code;
- Gemini;
- ChatGPT Work;
- future repository-aware AI agents.

An agent can stop midway and another agent should be able to continue from repository state using:

```bash
studium status
studium next
studium agent-pack
```

Important state should never live only inside an AI conversation.

## Academic state machine

A Studium project progresses through explicit stages:

```text
CREATED
   ↓
COURSE_DISCOVERY
   ↓
SOURCE_DISCOVERY
   ↓
CORPUS_BUILDING
   ↓
BLUEPRINT
   ↓
AUTHORING
   ↓
VERIFYING
   ↓
REVIEWING
   ↓
RELEASE_CANDIDATE
   ↓
RELEASED
```

Transitions depend on academic gates rather than merely whether files exist.

## LaTeX publishing

LaTeX is the primary publishing backend for Studium 1.x.

The shared publishing system is designed for:

- professional typography;
- print and tablet reading;
- mathematical typesetting;
- BibLaTeX/Biber bibliography;
- cross-references;
- indexes;
- figures and tables;
- TikZ/PGF diagrams;
- consistent pedagogical components.

```bash
studium build
```

The knowledge model is intentionally independent of LaTeX so other outputs can be added later.

## Releases are academic artifacts

A Studium release can contain more than the generated PDF.

```text
release/
└── 1.0/
    ├── book.pdf
    ├── certificate.json
    ├── CERTIFICATE.md
    ├── studium.lock
    └── manifest.json
```

The release certificate records which verification gates passed, what was not verified, relevant limitations, source state and reproducibility information.

Studium does **not** claim that a release is infallible.

It records that the release passed a defined and inspectable verification process.

## Core principles

> **AI output is not evidence.**

> **A source discovered is not necessarily a source verified.**

> **A citation must support the claim it accompanies.**

> **A solved problem deserves verification.**

> **Academic uncertainty should be represented, not hidden.**

> **A changed dependency invalidates stale reviews.**

> **The complexity belongs inside the framework, not in the student's workflow.**

## Architecture

The repository is organized around independent academic layers rather than one monolithic CLI.

```text
src/studium/
├── cli/             # User-facing commands
├── core/            # Domain models and shared primitives
├── config/          # Global and project configuration
├── research/        # Course and source discovery contracts
├── sources/         # Source registry and provenance
├── evidence/        # Claims and evidence
├── graph/           # Academic dependency graph
├── verification/    # Academic verification engines
├── orchestration/   # State machine and agent tasks
├── release/         # Lockfiles, manifests and certificates
├── latex/           # Publishing integration
└── domains/         # Domain-specific verification packs
```

For the full design, see [Architecture](./docs/architecture.md).

## Commands

The everyday interface is intentionally small.

| Command | Purpose |
|---|---|
| `studium create` | Create an academic project |
| `studium status` | Show current project state |
| `studium next` | Determine the next required task |
| `studium agent-pack` | Generate context for an AI agent |
| `studium run` | Follow the autonomous Studium workflow |
| `studium verify` | Run academic verification |
| `studium build` | Build the publication |
| `studium release` | Validate and create a release |
| `studium doctor` | Diagnose the local environment |

Advanced subcommands expose sources, claims, equations, derivations, exercises, reviews and the academic graph when needed.

## Development status

Studium is under active development toward its first stable release.

The `main` branch may change while the architecture, verification model and agent workflows are being validated.

The goal for **Studium 1.0** is to demonstrate the complete workflow:

```text
course + university + degree
              ↓
verified academic research
              ↓
complete course knowledge model
              ↓
professionally authored study material
              ↓
academic verification
              ↓
release-ready textbook
```

without requiring the student to manually design the research pipeline.

## Documentation

| Topic | Document |
|---|---|
| Architecture | [`docs/architecture.md`](./docs/architecture.md) |
| Research model | [`docs/research-model.md`](./docs/research-model.md) |
| Evidence model | [`docs/evidence-model.md`](./docs/evidence-model.md) |
| Verification model | [`docs/verification-model.md`](./docs/verification-model.md) |
| AI orchestration | [`docs/ai-orchestration.md`](./docs/ai-orchestration.md) |
| Domain packs | [`docs/domain-packs.md`](./docs/domain-packs.md) |
| Release model | [`docs/release-model.md`](./docs/release-model.md) |
| Security | [`docs/security.md`](./docs/security.md) |
| Copyright | [`docs/copyright.md`](./docs/copyright.md) |

## Contributing

Studium welcomes focused contributions to the framework, research protocols, verification engines, LaTeX publishing system, domain packs and documentation.

Before submitting a pull request:

1. keep the change scoped;
2. add or update tests;
3. run the relevant validation;
4. document changes to schemas or public behaviour;
5. do not commit copyrighted or private academic source material.

Development setup:

```bash
git clone https://github.com/danielmigueltejedor/studium.git
cd studium

python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

pytest
```

See [`CONTRIBUTING.md`](./CONTRIBUTING.md) for the full development workflow.

## Security and privacy

Source files may contain private educational material or personal information.

Studium should never automatically upload local sources to public repositories or external services.

Please report security issues according to [`SECURITY.md`](./SECURITY.md).

## License

Studium is released under the [Apache License 2.0](./LICENSE).

The Studium license applies to the framework itself. Books and other outputs created with Studium are **not automatically licensed under Apache-2.0**. Authors remain responsible for selecting an appropriate license for generated works and for respecting the rights of all source material used.

<div align="center">
  <sub>Created and maintained by <a href="https://github.com/danielmigueltejedor">Daniel Miguel Tejedor</a>.</sub>
</div>
