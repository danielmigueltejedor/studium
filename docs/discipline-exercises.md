# Exercises by discipline

Studium used to treat every chapter's worked problem as a number: a replayed
computation or a numeric result cited from two excerpts. That fits an
engineering course. It does not fit a history, literature or law book, where
the first book built outside engineering ended up with "Colón recibe la décima
parte: calcule los maravedís". The exercise a discipline asks for is now chosen
by the book's domain profile.

## What each profile accepts

| Profile | Numeric / Rust problem | Discursive exercise types |
| --- | --- | --- |
| `STEM`, `COMPUTER_SCIENCE` | yes (Rust only in computer science) | none |
| `LIFE_SCIENCES` | yes | `EXPERIMENT_DESIGN`, `DATA_INTERPRETATION`, `MECHANISM_EXPLANATION`, `CAUSAL_ANALYSIS`, `DEVELOPMENT_QUESTION`, `COMPARATIVE`, `CONCEPTUAL` |
| `SOCIAL_SCIENCES` | yes | `DEVELOPMENT_QUESTION`, `SOURCE_COMMENTARY`, `CASE_ANALYSIS`, `CAUSAL_ANALYSIS`, `DATA_INTERPRETATION`, `CHRONOLOGY`, `COMPARATIVE`, `CONCEPTUAL` |
| `HUMANITIES` | **refused** | `DEVELOPMENT_QUESTION`, `SOURCE_COMMENTARY`, `TEXT_COMMENTARY`, `LITERARY_ANALYSIS`, `CHRONOLOGY`, `CAUSAL_ANALYSIS`, `COMPARATIVE`, `CONCEPTUAL` |
| `LAW` | **refused** | `DEVELOPMENT_QUESTION`, `SOURCE_COMMENTARY`, `CASE_ANALYSIS`, `CAUSAL_ANALYSIS`, `COMPARATIVE`, `CONCEPTUAL` |
| `GENERAL` | yes | all |

A refused numeric problem returns `problem.numeric_not_for_discipline` with the
types the profile does accept. A type that belongs to another discipline
returns `problem.type_not_for_discipline`.

## Recording one

`studium_problem_record` takes a discursive `problem_type` plus:

* `answer` — the model answer (*pauta*): `summary`, `sections` of labelled
  `points`, `mistakes`, `criteria`. A `CHRONOLOGY` takes `events` (three or more)
  instead of `sections`.
* `source` — for `SOURCE_COMMENTARY`, `TEXT_COMMENTARY` and `LITERARY_ANALYSIS`,
  the passage the reader comments: `{excerpt, quote, author?, work?, date?}`.
  Verses go on separate lines of `quote`.
* `questions` — guiding questions.

Every point and event cites one to four stored excerpt ids.

## What is checked

The checks are mechanical and narrow:

* every cited excerpt exists and passes the same citation rules as a paragraph;
* the quoted source text is a verbatim passage of the excerpt it names;
* a chronology event's year appears in the text of an excerpt the event cites;
* the answer is `two_witnesses` only when its excerpts come from at least two
  different sources.

That is agreement between sources. It does not say the sources are right and it
is not an academic review. A discursive worked exercise counts as the chapter's
worked problem only when it is `two_witnesses`; a practice exercise is printed
with its model answer in the solutions appendix under the same condition.

## Rendering

The worked exercise prints *Enunciado*, *Texto para comentar* (a quotation with
author, work and date), *Cuestiones* and *Pauta de respuesta*; a chronology
prints as a dated list sorted by year. Practice exercises print the statement,
the text and the questions; the answers go to the solutions appendix.

# Image figures

`studium_figure_record` also accepts `kind: "image"` for a picture taken from an
open source (a map, a manuscript page, a micrograph). It takes an `image` object
`{path, url, title, author, license, license_url?, credit?, date?}`.

* `path` is the PNG or JPEG the client already downloaded **inside the book**
  (200 to 6000 pixels a side, at most 3 MB). The server never fetches the URL.
* `license` must be public domain, CC0, CC BY or CC BY-SA. Anything else is
  refused with `figure.license_not_allowed`. A missing author, title or page is
  refused.
* `studium_figure_check` stores the file hash and copies the file to
  `figures/<id>/figure.png|jpg`; the picture renders only while the file keeps
  that hash.
* The credit (author, title, licence, page) prints under the picture and in a
  *Créditos de las figuras* list before the bibliography.

This is provenance and licence bookkeeping. The licence text the client read on
the source page can be wrong, and nothing here is a legal opinion.

TikZ figures are now checked with the libraries the book loads
(`arrows.meta`, `positioning`, `calc`, `shapes.geometric`), so a drawing that
renders in the book can also be checked.
