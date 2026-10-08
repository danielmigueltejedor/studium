<div align="center">
  <img src="docs/assets/studium-logo.png" alt="Studium" width="420">

  <p><strong>Draft an evidence-grounded study book with an AI client. The model is not a source of truth.</strong></p>

  <p>
    <a href="https://github.com/danielmigueltejedor/studium/actions">
      <img src="https://img.shields.io/github/actions/workflow/status/danielmigueltejedor/studium/ci.yml?branch=main&label=CI&logo=github" alt="CI">
    </a>
    <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white" alt="Python 3.11+">
    <img src="https://img.shields.io/badge/LaTeX-native-008080?logo=latex&logoColor=white" alt="LaTeX">
    <a href="./LICENSE">
      <img src="https://img.shields.io/badge/license-Apache--2.0-2EA44F" alt="Apache License 2.0">
    </a>
  </p>
</div>

---

Studium stores sources, excerpts, chapters, checks, and a draft PDF. It does not treat model prose as evidence, and it does not publish a book.

A draft is `latex/draft.tex` and, when a compiler is on `PATH`, `latex/draft.pdf`. Publication is not implemented. The CLI does not provide `studium run`, `studium build`, or `studium release`. `studium render` writes the draft. `studium verify` returns blockers and does not move the book to `RELEASED`.

`audit_passed` means this edition's audits still match the current paragraph and excerpt text and each one cites a tool result the server already stored. It does not mean the prose was mathematically verified, academically reviewed, or published. A changed paragraph or excerpt makes that audit stale. `studium_verify` still refuses release.

The tool to follow is **`studium_book_next`**. It reads the book files and returns the next concrete tool call. A new session can resume from those files. It does not resume from chat memory, and it does not loop. Call it and perform the tool it names. Do not ask the user what to do next when that step can be done from open sources or from files already given.

## The 1.0 path

```text
create a course book or a topic book
        ↓
optional local files the user already has
        ↓
the client searches and records open sources
        ↓
opened excerpts
        ↓
long chapters
        ↓
checks (COMPUTATION_REPRODUCED, two excerpts, or a rustc reproducibility check for code)
        ↓
audit
        ↓
contradiction scan
        ↓
review
        ↓
draft PDF
```

1. Create the book. A course book needs a slug, course, university, and degree. A topic book needs a slug and topic and does not ask for a university guide. A programming topic uses profile `COMPUTER_SCIENCE`. Engineering, physics, and math use `STEM`.
2. Local files are optional. If the user already has notes or a problem sheet, record those files. They are input, not authority.
3. The client searches the open web, opens the page, and records the source with `studium_public_source_record`. Record only a URL you actually opened. The server does not fetch it.
4. Store an excerpt of the page you read before writing from it.
5. Write chapters in the shape below. Cite stored excerpts. A formula is accepted only when that formula is quoted in a cited excerpt or replayed by `studium_computation_check`.
6. Check the worked problem. Audit the chapter against stored tool results. Scan for contradictions. Review the edition. Render the draft.

`studium_book_next` will not tell the client to render while any of these fail:

- fewer than 8 blueprint sections
- fewer than 12 distinct sources (user-provided local files and recorded open-web sources both count; pirate copies and licenses that forbid this use do not)
- a written chapter with fewer than two explanation sections, under 400 words of explanation, or without the lead, one tip, one worked problem, and one self-check
- a worked problem whose resolution is only an arithmetic expression
- a Rust test used as the worked problem of a book whose profile is not `COMPUTER_SCIENCE`

While one of those is open, the next action is to write that chapter. The reason names the chapter and the missing contract pieces. A partial PDF is not a reason to stop. Render once only after every planned chapter meets the contract. The book stays unreleased.

## Chapter shape

Every chapter uses the same shape:

- a short lead
- at least two blocks of explanation, as body text, not one section titled with the framework word for explanation
- at most one tip
- definitions only when a term is introduced
- one worked problem with a statement, a solution, and an answer
- one self-check

The visible titles follow the book language. A Spanish book uses Consejo, Definición, Problema resuelto, Autoficha, Enunciado, Resolución, and Respuesta. Explanation stays body text.

A worked problem in a STEM or general book is a replayed computation or a numeric result cited from two excerpts. A book whose profile is not `COMPUTER_SCIENCE` must not use a Rust test as that worked problem. A programming book may keep a Rust test. Three identical `rustc` runs are a reproducibility check, not an independent proof, and not three methods. A computation replayed by the same expression is `COMPUTATION_REPRODUCED` in the audit record. That is not mathematically verified and not academically reviewed. Two excerpts that agree are `two_witnesses`, not verified and not absolute truth.

Unchecked figures stay out of the chapter. `studium_figure_remove` deletes one figure by id. A checked figure stays inline, capped, with the caption under the image. Boxes are only the tip, the definition, the worked problem, and the self-check. Explanation is body text.

Without a course guide, the blueprint is a study book: roadmap, foundations, the topic chapters, worked problems, self-check, a formula or concept sheet, and the source audit. With a guide, chapters follow the guide and the same chapter contract applies.

Set `--language` at creation for a course book or a topic book. A BCP 47 tag (`es`, `en`, `fr`, `de`, `pt`, `it`, `ca`, `gl`, `pt-BR`) or a TeX babel name (`spanish`, `dutch`) is stored on the project. An empty or unknown code is rejected. A project with no language stays Spanish, so an old `programacion`, `fluidos`, or `rust` book does not change. The draft loads that babel language. Hyphenation, captions, and `\today` follow it. Chrome (cover draft status, box titles, problem labels, contents title, and audit headings) is translated for Spanish, English, French, German, Portuguese, Italian, Catalan, and Galician. A babel language with no catalog entry uses English chrome. Chapter prose is not translated. `studium_book_next` tells the writer to draft in the book's language.

## What the client runs

Start the MCP server and follow `studium_book_next`:

```bash
studium mcp
```

Create a book from the CLI if you are not using MCP:

```bash
studium create fluidos \
  --course "Mecánica de Fluidos" \
  --university "Universidad de León" \
  --degree "Grado en Ingeniería Aeroespacial"

studium create rust --topic "Rust"
```

Optional local files:

```bash
studium sources add ./notes.pdf --project fluidos
```

Render writes `latex/draft.tex` and compiles `latex/draft.pdf` when `pdflatex` or `tectonic` is on `PATH`. A missing compiler does not pretend a PDF exists. The file is a draft.

```bash
studium render --project fluidos
```

`studium verify --full` returns blockers. It does not move the book to `RELEASED`.

## Install

```bash
git clone https://github.com/danielmigueltejedor/studium.git
cd studium

python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

Name that environment `venv`. On macOS, iCloud Drive can hide files inside a directory whose name starts with a dot, and Python then skips the editable-install path file.

```bash
pytest
```

## Principles

- The model is not a source of truth.
- A formula must be quoted in a stored excerpt or replayed by the server.
- Pirate copies and licenses that forbid this use are refused. OpenStax is one such license.
- `audit_passed` is for this edition only. It does not publish the book.
- Unchecked prose may appear in the draft and is labeled unchecked.

## Documentation

| Topic | Document |
|---|---|
| Research model | [`docs/research-model.md`](./docs/research-model.md) |
| Evidence model | [`docs/evidence-model.md`](./docs/evidence-model.md) |
| AI orchestration | [`docs/ai-orchestration.md`](./docs/ai-orchestration.md) |
| Verification model | [`docs/verification-model.md`](./docs/verification-model.md) |
| Release model | [`docs/release-model.md`](./docs/release-model.md) |

The release model describes gates that are not a publisher. This version does not implement a release that publishes a book.

## Contributing

Keep the change scoped, add tests, and run `pytest`. Do not commit private course files. See [`CONTRIBUTING.md`](./CONTRIBUTING.md).

## License

Studium is released under the [Apache License 2.0](./LICENSE).

Books created with Studium are not automatically licensed under Apache-2.0. Authors remain responsible for the rights of the sources they use.

<div align="center">
  <sub>Created and maintained by <a href="https://github.com/danielmigueltejedor">Daniel Miguel Tejedor</a>.</sub>
</div>
