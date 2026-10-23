"""LaTeX output adapter for a draft. This is not a release build.

Writes ``latex/draft.tex``. Compiles ``latex/draft.pdf`` only when tectonic
or pdflatex is on PATH. A failed attempt preserves the previous PDF.
"""

import os
import re
import shutil
import subprocess
import unicodedata
import urllib.parse
from contextvars import ContextVar
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from studium.authoring import exercises, figure_images
from studium.authoring.academic_blueprint import current_academic_blueprint
from studium.authoring.blueprint import current_sections
from studium.authoring.computation import ComputationError, current_computations, evaluate
from studium.authoring.derivations import derivations_for_section
from studium.authoring.diagrams import diagram_state, problem_figures, renderable
from studium.authoring.excerpts import excerpts_by_id
from studium.authoring.figure_artifacts import checked_figure_output
from studium.authoring.figures import FIGURE_REF, figure_reference_map, figures_in_section, referenced_figure_keys
from studium.authoring.grounding import FORMULA_STATUSES, GroundingContext, formula_statuses
from studium.authoring.languages import (
    INVALID_LANGUAGE,
    BookLanguage,
    book_language,
    generic_section_titles,
    messages,
)
from studium.authoring.literals import code_regions
from studium.authoring.mathematics import DEFAULT_SYMBOL_NAMES, MathError, numeric_latex, symbolic_latex, unit_latex
from studium.authoring.notation import notation_registry
from studium.authoring.paragraphs import supported_paragraphs
from studium.authoring.problems import problem_result_current
from studium.authoring.publishing import align_long_chain, editorial_report, record_lines, write_report
from studium.authoring.support import corroboration_for_excerpts, supported_drafts
from studium.diagrams.registry import Options as DiagramOptions
from studium.diagrams.registry import family_laws
from studium.domain.profiles import BOOK_TOPIC
from studium.research.public_sources import bibliography_counts
from studium.storage.init_project import book_kind, load_project_toml, load_state_holding_lock
from studium.storage.init_project import domain_profile as _domain_profile
from studium.storage.locking import ProjectLocked, project_lock
from studium.storage.records import (
    AUDITS,
    DERIVATIONS,
    EXCERPTS,
    FIGURES,
    PARAGRAPHS,
    PROBLEMS,
    PUBLIC_BIBLIOGRAPHY,
    fold_by_id,
)

_REVIEW_RENDERING: ContextVar[bool] = ContextVar("studium_review_rendering", default=False)
# Lower-cased keys of the figures this render draws. ``None`` outside a render,
# where every ``{{fig:key}}`` is still written as a numbered reference.
_DRAWN_FIGURE_KEYS: ContextVar[frozenset[str] | None] = ContextVar("studium_drawn_figure_keys", default=None)
_TEX_NAME = "draft.tex"
_PDF_NAME = "draft.pdf"
_LABEL_SAFE = re.compile(r"[^A-Za-z0-9._:-]")


def _str_field(record: dict[str, object], key: str, default: str = "") -> str:
    value = record.get(key)
    return value if isinstance(value, str) else default


def _list_field(record: dict[str, object], key: str) -> list[object]:
    value = record.get(key)
    return value if isinstance(value, list) else []


def _label(prefix: str, identifier: str) -> str:
    safe = _LABEL_SAFE.sub("-", identifier)
    return r"\label{" + prefix + ":" + safe + "}"


_LATEX = {
    "\\": r"\textbackslash{}",
    "{": r"\{",
    "}": r"\}",
    "$": r"\$",
    "%": r"\%",
    "&": r"\&",
    "#": r"\#",
    "_": r"\_",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}
_GREEK = {
    "Α": r"\mathrm{A}",
    "Β": r"\mathrm{B}",
    "Γ": r"\Gamma",
    "Δ": r"\Delta",
    "Ε": r"\mathrm{E}",
    "Ζ": r"\mathrm{Z}",
    "Η": r"\mathrm{H}",
    "Θ": r"\Theta",
    "Ι": r"\mathrm{I}",
    "Κ": r"\mathrm{K}",
    "Λ": r"\Lambda",
    "Μ": r"\mathrm{M}",
    "Ν": r"\mathrm{N}",
    "Ξ": r"\Xi",
    "Ο": r"\mathrm{O}",
    "Π": r"\Pi",
    "Ρ": r"\mathrm{P}",
    "Σ": r"\Sigma",
    "Τ": r"\mathrm{T}",
    "Υ": r"\Upsilon",
    "Φ": r"\Phi",
    "Χ": r"\mathrm{X}",
    "Ψ": r"\Psi",
    "Ω": r"\Omega",
    "α": r"\alpha",
    "β": r"\beta",
    "γ": r"\gamma",
    "δ": r"\delta",
    "ε": r"\varepsilon",
    "ζ": r"\zeta",
    "η": r"\eta",
    "θ": r"\theta",
    "ι": r"\iota",
    "κ": r"\kappa",
    "λ": r"\lambda",
    "μ": r"\mu",
    "ν": r"\nu",
    "ξ": r"\xi",
    "ο": r"o",
    "π": r"\pi",
    "ρ": r"\rho",
    "σ": r"\sigma",
    "ς": r"\varsigma",
    "τ": r"\tau",
    "υ": r"\upsilon",
    "φ": r"\varphi",
    "χ": r"\chi",
    "ψ": r"\psi",
    "ω": r"\omega",
    "ℓ": r"\ell",
    "×": r"\times",
    "·": r"\cdot",
    "−": r"-",
    "–": r"-",
    "—": r"-",
    "≤": r"\leq",
    "≥": r"\geq",
    "±": r"\pm",
    "∞": r"\infty",
    "∂": r"\partial",
    "∇": r"\nabla",
    "≈": r"\approx",
    "≠": r"\neq",
    "°": r"^{\circ}",
    "′": r"'",
}
_SUBSCRIPTS = {chr(0x2080 + index): f"_{{{index}}}" for index in range(10)}
_SUBSCRIPTS.update(
    {
        "₊": r"_{+}",
        "₋": r"_{-}",
        "₌": r"_{=}",
        "ₐ": r"_{a}",
        "ₑ": r"_{e}",
        "ₒ": r"_{o}",
        "ₓ": r"_{x}",
        "ₕ": r"_{h}",
        "ₖ": r"_{k}",
        "ₗ": r"_{l}",
        "ₘ": r"_{m}",
        "ₙ": r"_{n}",
        "ₚ": r"_{p}",
        "ₛ": r"_{s}",
        "ₜ": r"_{t}",
    }
)
_SUPERSCRIPTS = {
    "⁰": r"^{0}",
    "¹": r"^{1}",
    "²": r"^{2}",
    "³": r"^{3}",
    "⁴": r"^{4}",
    "⁵": r"^{5}",
    "⁶": r"^{6}",
    "⁷": r"^{7}",
    "⁸": r"^{8}",
    "⁹": r"^{9}",
    "⁺": r"^{+}",
    "⁻": r"^{-}",
    "ⁿ": r"^{n}",
    "ⁱ": r"^{i}",
}
#: Unicode operators that carry no analogue in the Greek/sub/superscript maps.
#: ``√`` is listed with a bare radical as a fallback for the plain-escape path;
#: the formula renderer consumes its argument and emits ``\sqrt{...}``.
_MATH_EXTRA = {
    "µ": r"\mu",
    "⋅": r"\cdot",
    "∝": r"\propto",
    "≡": r"\equiv",
    "⇒": r"\Rightarrow",
    "⇔": r"\Leftrightarrow",
    "→": r"\to",
    "←": r"\leftarrow",
    "÷": r"\div",
    "√": r"\surd",
    "∛": r"\sqrt[3]{}",
    "∜": r"\sqrt[4]{}",
    "∑": r"\sum",
    "∏": r"\prod",
    "∫": r"\int",
    "∘": r"\circ",
    "⊥": r"\perp",
    "∠": r"\angle",
    "∆": r"\Delta",
    "∈": r"\in",
    "∅": r"\varnothing",
    "½": r"\frac{1}{2}",
    "⅓": r"\frac{1}{3}",
    "⅔": r"\frac{2}{3}",
    "¼": r"\frac{1}{4}",
    "¾": r"\frac{3}{4}",
    "⅕": r"\frac{1}{5}",
    "⅖": r"\frac{2}{5}",
    "⅗": r"\frac{3}{5}",
    "⅘": r"\frac{4}{5}",
    "ṁ": r"\dot{m}",
    "ẋ": r"\dot{x}",
    "ẏ": r"\dot{y}",
    "ṫ": r"\dot{t}",
    "ṙ": r"\dot{r}",
    "ṗ": r"\dot{p}",
    "ṡ": r"\dot{s}",
    "ż": r"\dot{z}",
    "ẇ": r"\dot{w}",
}
#: Radical sign -> the optional root index inside ``\sqrt[...]``.
_ROOTS = {"√": "", "∛": "3", "∜": "4"}
_MATH = {**_GREEK, **_SUBSCRIPTS, **_SUPERSCRIPTS, **_MATH_EXTRA}

#: Characters that cannot stand alone as the base of a super/subscript. A script
#: run that follows one of these (or starts the run) is given an empty group so
#: the output stays valid LaTeX.
_NO_BASE = set(" \t=+-*/,(<>|")


def _script_inner(value: str) -> str:
    """The content of a ``^{...}`` or ``_{...}`` mapping, without the group."""

    return value[2:-1]


def _root_argument(text: str, index: int) -> tuple[str, int]:
    r"""The argument of a Unicode radical at ``index``.

    Accepts a braced group, a parenthesised group, one alphanumeric run, or one
    single math character. The parentheses around a radical argument are not
    part of the argument, so ``√(g h)`` becomes ``\sqrt{g h}``.
    """

    if index >= len(text):
        return "", index
    opener = text[index]
    if opener in "{(":
        closer = "}" if opener == "{" else ")"
        depth = 0
        cursor = index
        while cursor < len(text):
            character = text[cursor]
            if character == opener:
                depth += 1
            elif character == closer:
                depth -= 1
                if depth == 0:
                    return text[index + 1 : cursor], cursor + 1
            cursor += 1
        return text[index + 1 :], len(text)
    if opener.isalnum():
        cursor = index
        while cursor < len(text) and text[cursor].isalnum():
            cursor += 1
        return text[index:cursor], cursor
    if opener in _MATH:
        return text[index], index + 1
    return "", index


def _map_math_run(text: str, *, escape: bool = False) -> str:
    r"""Translate a run of Unicode mathematics into LaTeX math content.

    Greek and operator characters map to control words; a consecutive run of
    Unicode super- or subscripts becomes a single braced group (so ``⁻³`` is
    ``^{-3}``, never a double superscript); a radical consumes its argument and
    becomes ``\sqrt{...}``. ASCII mathematics (``_``, ``^``, ``{``, ``}``) is
    passed through unchanged, so author-written ``p_{man}`` stays valid.
    """

    parts: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        character = text[index]
        if character in _ROOTS:
            index += 1
            inner, index = _root_argument(text, index)
            option = _ROOTS[character]
            head = r"\sqrt" + (f"[{option}]" if option else "")
            parts.append(head + "{" + _map_math_run(inner, escape=escape) + "}")
            continue
        if character in _SUPERSCRIPTS or character in _SUBSCRIPTS:
            superscript = character in _SUPERSCRIPTS
            table = _SUPERSCRIPTS if superscript else _SUBSCRIPTS
            run: list[str] = []
            while index < length and text[index] in table:
                run.append(_script_inner(table[text[index]]))
                index += 1
            tail = parts[-1] if parts else ""
            if not tail or tail[-1] in _NO_BASE:
                parts.append("{}")
            parts.append(("^" if superscript else "_") + "{" + "".join(run) + "}")
            continue
        # Group an ASCII subscript when it is immediately followed by
        # a Unicode superscript. For example:
        # V_entrada² -> V_{entrada}^{2}
        #
        # Keep ordinary author-written ASCII notation unchanged.
        if character == "_" and index + 1 < length:
            cursor = index + 1

            while (
                cursor < length
                and text[cursor].isascii()
                and text[cursor].isalnum()
            ):
                cursor += 1

            if (
                cursor > index + 1
                and cursor < length
                and text[cursor] in _SUPERSCRIPTS
            ):
                parts.append(
                    "_{" + text[index + 1:cursor] + "}"
                )
                index = cursor
                continue

        mapped = _MATH.get(character)
        if mapped is not None:
            if mapped.startswith("\\") and mapped[-1:].isalpha():
                following = text[index + 1] if index + 1 < length else ""
                if following.isascii() and following.isalpha():
                    mapped += " "
            parts.append(mapped)
            index += 1
            continue
        if escape and character in "%#&":
            parts.append("\\" + character)
            index += 1
            continue
        if escape and character == "\\":
            parts.append(r"\backslash ")
            index += 1
            continue
        parts.append(character)
        index += 1
    return _brace_ascii_exponents("".join(parts))


# TeX raises only the first character of ``10^14``. A multi-digit or negative
# exponent typed in ASCII needs its braces.
_UNBRACED_EXPONENT = re.compile(r"\^(-\d+|\d{2,})")


def _brace_ascii_exponents(tex: str) -> str:
    return _UNBRACED_EXPONENT.sub(lambda match: "^{" + match.group(1) + "}", tex)


def render_draft(root: Path, *, include_unsupported: bool = False) -> dict[str, object]:
    """Write a DRAFT .tex of the blueprint and supported claims, then compile if possible."""

    try:
        with project_lock(root):
            return _render_holding_lock(root, include_unsupported=include_unsupported)
    except UnsupportedLiteralCharacter as error:
        return _error("render.unsupported_literal_character", str(error))
    except ProjectLocked:
        return _error("storage.locked", "project is locked")
    except OSError:
        return _error("render.write_failed", "the draft attempt could not be written; publication recovery copies are under .studium/render-backups")


def _render_holding_lock(root: Path, *, include_unsupported: bool) -> dict[str, object]:
    state = load_state_holding_lock(root)
    tex_path, pdf_path = _outputs(root)
    if tex_path is None or pdf_path is None:
        return _error("render.path_escaped", "draft path leaves the project")
    if tex_path.is_symlink() or pdf_path.is_symlink():
        return _error("render.path_escaped", "draft artifacts must not be symlinks")
    if book_language(root) is None:
        return _error("render.invalid_language", INVALID_LANGUAGE)
    document = _document(root, include_unsupported=include_unsupported)
    tex_path.parent.mkdir(parents=True, exist_ok=True)
    # A sibling of latex keeps authored ../figures and ../editorial-config
    # references valid. Compiler intermediates never touch the current edition.
    with TemporaryDirectory(prefix=".studium-render-", dir=root) as temporary:
        attempt = Path(temporary) / _TEX_NAME
        attempt.write_text(document, encoding="utf-8")
        body = _render_attempt(root, attempt, document, state, include_unsupported=include_unsupported)
        succeeded = body.get("pdf") is not None
        preserve = pdf_path.exists()
        if succeeded and preserve:
            # Recovery copy precedes every replacement. Files are individually
            # atomic; this is deliberately not a multi-file filesystem transaction.
            backup = root / ".studium" / "render-backups" / uuid4().hex
            try:
                backup.resolve().relative_to(root.resolve())
            except ValueError as exc:
                raise OSError("render backup leaves the project") from exc
            backup.mkdir(parents=True)
            for previous in tex_path.parent.glob("draft.*"):
                if previous.is_symlink():
                    raise OSError("refusing a symlinked render artifact")
                if previous.is_file():
                    shutil.copy2(previous, backup / previous.name)
            body["previous_artifacts"] = _relative(root, backup)
        failed_prefix = "draft.failed" if preserve and not succeeded else "draft"
        for artifact in sorted(Path(temporary).glob("draft.*"), key=lambda path: path.suffix == ".pdf"):
            if artifact.suffix == ".pdf" and not succeeded:
                continue
            destination = tex_path.parent / (failed_prefix + artifact.name[len("draft"):])
            with artifact.open("rb") as stream:
                os.fsync(stream.fileno())
            os.replace(artifact, destination)
        body["tex"] = "latex/" + failed_prefix + ".tex"
        body["editorial_report"] = "latex/" + failed_prefix + ".quality.json"
        if body.get("compiler_log") is not None:
            body["compiler_log"] = "latex/" + failed_prefix + ".compiler.log"
        if preserve and not succeeded:
            body["previous_pdf"] = _relative(root, pdf_path)
        return body


def _render_attempt(
    root: Path, tex_path: Path, document: str, state: dict[str, object], *, include_unsupported: bool
) -> dict[str, object]:
    pdf_path = tex_path.with_suffix(".pdf")
    local = _local(state)
    project_state = state.get("state")
    engine = find_engine()
    unwritten = _first_unwritten_title(root, include_unsupported=include_unsupported)
    body = {
        "includes_unsupported_drafts": include_unsupported,
        "tex": "latex/draft.tex",
        "pdf": None,
        "released": project_state == "RELEASED",
        "project_state": project_state,
        "local_sources": local,
        "draft_claims": [str(claim["id"]) for claim in supported_drafts(root) if isinstance(claim.get("id"), str)],
        "draft_paragraphs": [
            str(paragraph["id"]) for paragraph in supported_paragraphs(root) if isinstance(paragraph.get("id"), str)
        ],
    }
    if engine is None:
        _save_editorial_report(tex_path, document, "", False, None, body)
        message = (
            "no LaTeX engine on PATH (tectonic or pdflatex). "
            "Wrote the .tex draft. No PDF was created."
        )
        return _render_status(body, status="compiler_missing", message=message, unwritten=unwritten)
    compiled, detail = _compile(engine, tex_path, tex_path.parent)
    process_log = tex_path.with_suffix(".compiler.log")
    log_path = tex_path.with_suffix(".log")
    log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
    if not compiled and not log:
        log = detail
    _save_editorial_report(tex_path, document, log, compiled and _is_pdf(pdf_path), engine, body)
    body["compiler_log"] = _relative(root, process_log) if process_log.is_file() else None
    if compiled and _is_pdf(pdf_path):
        body["pdf"] = "latex/draft.pdf"
        return _render_status(body, status="rendered", message="compiled a DRAFT PDF", unwritten=unwritten)
    if pdf_path.exists():
        pdf_path.unlink()
    message = "the LaTeX engine failed. Wrote the .tex draft. No PDF was created."
    if detail:
        message = f"{message} {detail}"
    missing = _missing_latex_packages(log + "\n" + detail)
    if missing:
        body["missing_latex_packages"] = missing
        message = (
            f"{message} The TeX installation lacks {', '.join(missing)}; "
            f"install with: tlmgr install {' '.join(missing)}"
        )
    return _render_status(body, status="render.compile_failed", message=message, unwritten=unwritten)


_MISSING_STYLE = re.compile(r"File [`']([A-Za-z0-9_.+-]+)\.(?:sty|cls)' not found")


def _missing_latex_packages(log: str) -> list[str]:
    """Packages a failed compile could not find, in order, without duplicates.

    A basic TeX Live lacks packages such as ``accsupp``; the raw log ended in a
    bare engine failure and the cause had to be read from it by hand.
    """

    found: list[str] = []
    for name in _MISSING_STYLE.findall(log):
        if name not in found:
            found.append(name)
    return found


def _save_editorial_report(
    tex_path: Path, document: str, log: str, compiled: bool, engine: str | None, body: dict[str, object]
) -> None:
    report = editorial_report(document, log, filename=tex_path.name, compiled=compiled, compiler=engine)
    path = tex_path.with_suffix('.quality.json')
    write_report(path, report)
    body['editorial_report'] = 'latex/' + path.name
    body['editorial_counts'] = report['counts']


def _render_status(
    body: dict[str, object],
    *,
    status: str,
    message: str,
    unwritten: str | None,
) -> dict[str, object]:
    """A compiled draft with an unwritten chapter is incomplete, not finished."""

    if unwritten is None:
        return {"status": status, "message": message, **body}
    note = f"The book is incomplete. Write the next unwritten chapter: {unwritten}."
    if status != "rendered":
        note = f"{note} {message}"
    return {"status": "incomplete", "message": note, "compile_status": status, **body}


def _first_unwritten_title(root: Path, *, include_unsupported: bool = False) -> str | None:
    paragraphs = ([r for r in fold_by_id(root / PARAGRAPHS) if r.get("status") == "draft"]
                  if include_unsupported else supported_paragraphs(root))
    covered = {record.get("section") for record in paragraphs}
    academic = current_academic_blueprint(root)
    if academic is not None:
        parts = academic.get("parts")
        if isinstance(parts, list):
            for part in parts:
                if not isinstance(part, dict):
                    continue
                for chapter in _iter_list(part.get("chapters")):
                    ch_id = _str_field(chapter, "id")
                    if ch_id and ch_id not in covered:
                        return _display_title(_str_field(chapter, "title"))
        return None
    for section in current_sections(root):
        if section["id"] not in covered:
            return _display_title(section["title"])
    return None


def _iter_list(value: object) -> list[dict[str, object]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def find_engine() -> str | None:
    for name in ("tectonic", "pdflatex"):
        found = shutil.which(name)
        if found:
            return found
    return None


def latex_escape(value: str) -> str:
    """Turn draft text into LaTeX that pdflatex can parse.

    Greek letters, subscripts, and operators such as Σ, ρ, ℓ, μ, and × become
    math commands. Latin letters stay as text so inputenc can read them.
    """

    parts: list[str] = []
    math: list[str] = []

    def flush_math() -> None:
        if math:
            parts.append(r"\(" + _map_math_run("".join(math)) + r"\)")
            math.clear()

    for character in value:
        if character in _MATH:
            math.append(character)
            continue
        flush_math()
        replacement = _LATEX.get(character)
        if replacement is not None:
            parts.append(replacement)
        elif ord(character) < 32 and character not in "\n\t":
            continue
        elif ord(character) > 255:
            parts.append(_fallback_character(character))
        else:
            parts.append(character)
    flush_math()
    return "".join(parts)


# Typography that arrives from sources and has a proper T1 command; anything else
# above U+00FF used to be printed as a literal ``U+XXXX`` in the PDF.
_TYPOGRAPHY = {
    "\u2026": r"\ldots{}",
    "\u2018": r"\textquoteleft{}",
    "\u2019": r"\textquoteright{}",
    "\u201c": r"\textquotedblleft{}",
    "\u201d": r"\textquotedblright{}",
    "\u201e": r"\quotedblbase{}",
    "\u2013": "--",
    "\u2014": "---",
    "\u2212": r"\ensuremath{-}",
    "\u00a0": "~",
    "\u2009": r"\,",
    "\u202f": r"\,",
    "\u2002": " ",
    "\u2003": " ",
}
_INVISIBLE = {"\u200b", "\u200c", "\u200d", "\u2060", "\ufeff", "\u00ad"}
_MACRON = {"\u0304"}


def _fallback_character(character: str) -> str:
    """A command for a character outside Latin-1 that pdflatex cannot read directly.

    Invisible format characters vanish, typographic punctuation maps to its T1
    command, and a letter with a decomposable mark keeps its base letter (with a
    macron where TeX can draw it). Only a character with no reading at all is
    shown as its code point, so the gap stays visible instead of silently lost.
    """

    if character in _INVISIBLE:
        return ""
    if character in _TYPOGRAPHY:
        return _TYPOGRAPHY[character]
    decomposed = unicodedata.normalize("NFD", character)
    if len(decomposed) > 1 and decomposed[0].isalpha() and decomposed[0].isascii():
        if all(mark in _MACRON for mark in decomposed[1:]):
            return "\\={" + decomposed[0] + "}"
        return decomposed[0]
    return f"{{U+{ord(character):04X}}}"


_ASCII_OPERATORS = set("=+-*/<>()[]{}^_|")
_STOP_LETTERS = set("yao")
_LISTINGS_LANGUAGE = {
    "python": "Python",
    "py": "Python",
    "c": "C",
    "h": "C",
    "cpp": "C++",
    "c++": "C++",
    "cc": "C++",
    "cxx": "C++",
    "java": "Java",
    "sql": "SQL",
    "html": "HTML",
    "xml": "XML",
    "tex": "TeX",
    "latex": "TeX",
    "bash": "bash",
    "sh": "sh",
    "shell": "bash",
    "r": "R",
    "ruby": "Ruby",
    "rb": "Ruby",
    "perl": "Perl",
    "php": "PHP",
    "lua": "Lua",
    "haskell": "Haskell",
    "hs": "Haskell",
    "matlab": "Matlab",
    "rust": "Rust",
    "rs": "Rust",
    "go": "Go",
    "golang": "Go",
    "js": "JavaScript",
    "javascript": "JavaScript",
    "typescript": "JavaScript",
    "ts": "JavaScript",
}
_PASS_ENVS = (
    "equation*",
    "align*",
    "gather*",
    "multline*",
    "flalign*",
    "eqnarray*",
    "equation",
    "align",
    "gather",
    "multline",
    "flalign",
    "eqnarray",
    "lstlisting",
    "verbatim",
    "Verbatim",
    "minted",
)
_MATH_ENVS = frozenset(
    {
        "equation*",
        "align*",
        "gather*",
        "multline*",
        "flalign*",
        "eqnarray*",
        "equation",
        "align",
        "gather",
        "multline",
        "flalign",
        "eqnarray",
    }
)
_FENCE_OPEN = re.compile(r"^[ ]{0,3}(`{3,}|~{3,})[ \t]*([A-Za-z0-9_+#.\-]*)[ \t]*$")
_ACCENTS = {
    "á": r"\'a",
    "é": r"\'e",
    "í": r"\'i",
    "ó": r"\'o",
    "ú": r"\'u",
    "à": r"\`a",
    "è": r"\`e",
    "ì": r"\`i",
    "ò": r"\`o",
    "ù": r"\`u",
    "ä": r"\"a",
    "ë": r"\"e",
    "ï": r"\"i",
    "ö": r"\"o",
    "ü": r"\"u",
    "ñ": r"\~n",
    "Ñ": r"\~N",
    "Á": r"\'A",
    "É": r"\'E",
    "Í": r"\'I",
    "Ó": r"\'O",
    "Ú": r"\'U",
    "Ü": r"\"U",
    "ç": r"\c{c}",
    "Ç": r"\c{C}",
    "¿": "?`",
    "¡": "!`",
}
_ESCAPE_DELIMS = (("(*@", "@*)"), ("(#@", "@#)"), ("(|@", "@|)"), ("[<@", "@>]"))
_BOX_STYLE = {
    "consejo": "studiumtip",
    "definition": "studiumdef",
    "worked": "studiumworked",
    "self_check": "studiumcheck",
    "exercise": "studiumworked",
    "derivation": "studiumdef",
}

#: Labels for the two boxes the language catalog does not carry. Spanish
#: books use Spanish; every other language uses the English default.
_EXTRA_BOX_LABELS: dict[str, dict[str, str]] = {
    "spanish": {
        "exercises": "Ejercicios",
        "exercise": "Ejercicio",
        "computations": "Cálculos reproducidos",
        "unassigned": "Sin capítulo asignado",
        "derivations": "Derivaciones",
        "symbol": "Símbolo",
        "meaning": "Significado",
        "units": "Unidades",
        "given": "Datos",
        "unknown": "Incógnita",
        "model": "Modelo físico",
        "model_generic": "Modelo",
        "assumptions": "Hipótesis",
        "principles": "Principios",
        "steps": "Pasos",
        "variables": "Variables",
        "boundaries": "Condiciones de contorno",
        "development": "Desarrollo",
        "substitution": "Sustitución numérica",
        "result": "Resultado",
        "interpretation": "Interpretación",
        "verification": "Comprobación de los pasos",
        "applicability": "Aplicabilidad",
        "limitations": "Limitaciones",
        "mistakes": "Errores frecuentes",
        "reproduced": "reproducido",
        "not_reproduced": "no reproducido",
        "ambiguous": "precisión ambigua",
        "step_word": "Paso",
        "answer_check": "Comprobación de la respuesta",
        "answer_replayed": "la aritmética del último paso reproduce la respuesta enunciada a la precisión con que está escrita. Es una reproducción aritmética; no valida el modelo físico ni sus hipótesis.",
        "answer_mismatch": "la aritmética del último paso no da la respuesta enunciada. La respuesta no está comprobada.",
        "answer_ambiguous": "la respuesta enunciada termina en ceros que pueden no ser significativos; sólo coincide si son de relleno. La respuesta no está comprobada.",
        "answer_unreplayable": "la respuesta no se pudo reproducir con los pasos almacenados. La respuesta no está comprobada.",
        "user_material": "Material aportado por el usuario (privado; no verificado).",
        "statement": "Enunciado",
        "free_body": "Diagrama de sólido libre",
        "equilibrium": "Equilibrio",
        "laws": "Solución matemática",
        "graphical": "Solución gráfica",
        "checks": "Verificación",
        "worked_number": "Problema resuelto",
        "worked_exercise": "Ejercicio resuelto",
        "figure_credits": "Créditos de las figuras",
        "source_text": "Texto para comentar",
        "questions": "Cuestiones",
        "answer_guide": "Pauta de respuesta",
        "criteria": "Criterios de evaluación",
        "chronology": "Cronología",
        "date": "Fecha",
        "event": "Hecho",
        "diagram_report": "Verificación de los diagramas",
        "diagram_intro": "Cada diagrama se dibuja a partir de los datos almacenados del problema y se comprueba aparte del dibujo. La tabla da el estado de cada uno; el detalle de las comprobaciones queda en el proyecto.",
        "diagram_figure": "Figura",
        "diagram_generator": "Generador",
        "diagram_status": "Estado",
        "diagram_checks": "Comprobaciones",
        "checks_sentence": "Comprobaciones automáticas sobre los datos del problema: {symbolic} exactas, {numeric} numéricas y {dimensional} dimensionales, todas superadas. Los diagramas se han comprobado punto a punto contra las funciones calculadas.",
        "checks_sentence_plain": "Comprobaciones automáticas sobre los datos del problema: {symbolic} exactas, {numeric} numéricas y {dimensional} dimensionales, todas superadas.",
        "mathematically_verified": "verificado matemáticamente",
        "numerically_checked": "comprobado numéricamente",
        "dimensionally_consistent": "dimensionalmente coherente",
        "visually_inspected": "inspeccionado visualmente",
        "not_machine_checkable": "no comprobable por máquina",
        "unverified": "sin comprobar",
        "verification_failed": "comprobación fallida",
        "stale": "desactualizado",
    },
}
_EXTRA_BOX_DEFAULTS = {
    "user_material": "User-provided material (private; not verified).",
    "exercises": "Exercises",
    "exercise": "Exercise",
    "computations": "Replayed calculations",
    "unassigned": "No assigned chapter",
    "derivations": "Derivations",
    "symbol": "Symbol",
    "meaning": "Meaning",
    "units": "Units",
    "given": "Given",
    "unknown": "Unknown",
    "model": "Physical model",
    "model_generic": "Model",
    "assumptions": "Assumptions",
    "principles": "Principles",
    "steps": "Steps",
    "variables": "Variables",
    "boundaries": "Boundary conditions",
    "development": "Development",
    "substitution": "Numerical substitution",
    "result": "Result",
    "interpretation": "Interpretation",
    "verification": "Step check",
    "applicability": "Applicability",
    "limitations": "Limitations",
    "mistakes": "Common mistakes",
    "reproduced": "reproduced",
    "ambiguous": "ambiguous precision",
    "answer_check": "Answer check",
    "answer_replayed": "the arithmetic of the final step reproduces the stated answer to the precision it is written with. This is an arithmetic reproduction; it does not validate the physical model or its assumptions.",
    "answer_mismatch": "the arithmetic of the final step does not give the stated answer. The answer is not checked.",
    "answer_ambiguous": "the stated answer ends in zeros that may not be significant; it agrees only if they are placeholders. The answer is not checked.",
    "answer_unreplayable": "the answer could not be reproduced from the stored steps. The answer is not checked.",
    "not_reproduced": "not reproduced",
    "step_word": "Step",
    "statement": "Problem statement",
    "free_body": "Free-body diagram",
    "equilibrium": "Equilibrium",
    "laws": "Mathematical solution",
    "graphical": "Graphical solution",
    "checks": "Verification",
    "worked_number": "Worked problem",
    "worked_exercise": "Worked exercise",
    "figure_credits": "Figure credits",
    "source_text": "Text to comment",
    "questions": "Questions",
    "answer_guide": "Model answer",
    "criteria": "Assessment criteria",
    "chronology": "Chronology",
    "date": "Date",
    "event": "Event",
    "diagram_report": "Diagram verification",
    "diagram_intro": "Every diagram is drawn from the problem's stored data and checked apart from the drawing. The table gives each one's status; the detailed checks stay in the project.",
    "diagram_figure": "Figure",
    "diagram_generator": "Generator",
    "diagram_status": "Status",
    "diagram_checks": "Checks",
    "checks_sentence": "Automatic checks on the problem data: {symbolic} exact, {numeric} numeric and {dimensional} dimensional, all passed. The diagrams were compared point by point with the computed functions.",
    "checks_sentence_plain": "Automatic checks on the problem data: {symbolic} exact, {numeric} numeric and {dimensional} dimensional, all passed.",
    "mathematically_verified": "mathematically verified",
    "numerically_checked": "numerically checked",
    "dimensionally_consistent": "dimensionally consistent",
    "visually_inspected": "visually inspected",
    "not_machine_checkable": "not machine-checkable",
    "unverified": "unverified",
    "verification_failed": "verification failed",
    "stale": "stale",
}

#: Verification statuses in prose. The raw enum name stays the fallback so a
#: status is never softened into a stronger claim.
_STATUS_PHRASES: dict[str, dict[str, str]] = {
    "spanish": {
        "SYMBOLICALLY_VERIFIED": "verificada simbólicamente",
        "DIMENSIONALLY_VERIFIED": "verificada dimensionalmente",
        "COMPUTATION_REPRODUCED": "cálculo rehecho",
        "NUMERICALLY_CROSS_CHECKED": "cruzada numéricamente",
        "INDEPENDENTLY_VERIFIED": "verificada por comprobaciones independientes",
        "UNVERIFIED": "sin comprobar",
        "FAILED": "comprobación fallida",
    },
}
_STATUS_PHRASE_DEFAULTS = {
    "SYMBOLICALLY_VERIFIED": "symbolically verified",
    "DIMENSIONALLY_VERIFIED": "dimensionally verified",
    "COMPUTATION_REPRODUCED": "computation replayed",
    "NUMERICALLY_CROSS_CHECKED": "numerically cross-checked",
    "INDEPENDENTLY_VERIFIED": "independently verified",
    "UNVERIFIED": "unchecked",
    "FAILED": "check failed",
}
_FUNC_WORDS = frozenset(
    {"sin", "cos", "tan", "log", "ln", "exp", "sqrt", "lim", "max", "min", "sum", "det", "gcd"}
)


def render_text_run(value: str) -> str:
    """Render emphasis around prose, code, and mathematics as a single span.

    Hide literal/formula contents while finding delimiters, so operators and
    strings inside those regions cannot open or close prose emphasis.
    """
    text = value.replace("\r\n", "\n").replace("\r", "\n")
    explicit = _explicit_spans(text)
    blocked = [(start, end) for start, end, _tex in explicit]
    masked = list(text)
    for start, end in blocked:
        masked[start:end] = [" " if char.isspace() else "X" for char in text[start:end]]
    pattern = re.compile(
        r"(?<![\w\\*])(\*\*\*|\*\*|\*)(?!\*)(?=\S)(.+?)(?<=\S)(?<!\*)\1(?!\*)",
        re.DOTALL,
    )
    parts: list[str] = []
    cursor = 0
    for match in pattern.finditer("".join(masked)):
        parts.append(_render_unstyled_text_run(text[cursor:match.start()]))
        body = render_text_run(text[match.start(2):match.end(2)])
        command = {"*": r"\emph", "**": r"\textbf", "***": r"\textbf{\emph"}[match[1]]
        parts.append(command + "{" + body + ("}}" if match[1] == "***" else "}"))
        cursor = match.end()
    parts.append(_render_unstyled_text_run(text[cursor:]))
    return "".join(parts)


def _render_unstyled_text_run(value: str) -> str:
    """Escape prose, keep explicit math, and wrap Unicode formulas in math mode."""

    text = value.replace("\r\n", "\n").replace("\r", "\n")
    # Code and explicit mathematics are opaque: prose normalization must not
    # change a program, identifier, or an author-supplied equation.
    opaque = _explicit_spans(text)
    for match in reversed(list(_SPELLED_DELTA.finditer(text))):
        if not any(start <= match.start() < end for start, end, _ in opaque):
            text = text[:match.start()] + "Δ" + text[match.end():]
    explicit = _explicit_spans(text)
    for match in _INTERNAL_IDENTIFIER.finditer(text):
        if not any(match.start() < end and match.end() > start for start, end, _ in explicit):
            explicit.append((match.start(), match.end(), latex_escape(match.group())))
    formulas = _formula_spans(text, explicit)
    events = [(start, end, tex) for start, end, tex in explicit]
    events.extend((start, end, _formula_tex(text[start:end])) for start, end in formulas)
    events.sort()
    parts: list[str] = []
    cursor = 0
    for start, end, tex in events:
        if start < cursor:
            continue
        if start > cursor:
            parts.append(latex_escape(text[cursor:start]))
        parts.append(tex)
        cursor = end
    if cursor < len(text):
        parts.append(latex_escape(text[cursor:]))
    return "".join(parts)


def emit_prose(value: str, *, italic: bool = False, figure_ref: str = "") -> list[str]:
    """Turn stored paragraphs into paragraphs, display math, and listings.

    ``figure_ref`` is the localized figure word (``figura``). When it is set,
    a ``{{fig:key}}`` marker becomes ``figura~\\ref{fig:key}``, so the number is
    produced by LaTeX and the author never maintains it.
    """

    text = value.replace("\r\n", "\n").replace("\r", "\n")
    lines: list[str] = []
    text_buf: list[str] = []

    def flush() -> None:
        if not text_buf:
            return
        chunk = "".join(text_buf)
        text_buf.clear()
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", chunk) if part.strip()]
        for paragraph in paragraphs:
            rendered = _render_figure_refs(paragraph, figure_ref)
            if _pure_inline_formula(paragraph, rendered):
                inner = rendered.strip()[2:-2].strip()
                lines.append("\\[\n" + inner + "\n\\]")
                continue
            if italic:
                lines.append(r"\noindent\textit{" + rendered + "}")
            else:
                lines.append(rendered)
            lines.append("")

    for kind, payload, extra in _split_blocks(text):
        if kind == "text":
            text_buf.append(payload)
            continue
        flush()
        if kind == "code":
            lines.extend(_listing_lines(payload, extra))
        else:
            lines.extend(_display_math(payload) if kind == "display" else [payload])
    flush()
    return lines


def _figure_label_key(key: str) -> str:
    """The LaTeX-safe label fragment two sides of a reference must agree on."""

    return _LABEL_SAFE.sub("-", key.strip().lower())


def _figure_ref_text(key: str, label: str) -> str:
    """Localized word plus a hyperlinked, auto-numbered ``\\ref``."""

    return latex_escape(label) + "~\\ref{fig:" + _figure_label_key(key) + "}"


def _render_figure_refs(paragraph: str, figure_ref: str) -> str:
    """Escape prose, resolving ``{{fig:key}}`` into a numbered reference."""

    if not figure_ref or "{{" not in paragraph:
        return render_text_run(paragraph)
    parts: list[str] = []
    cursor = 0
    drawn = _DRAWN_FIGURE_KEYS.get()
    for match in FIGURE_REF.finditer(paragraph):
        parts.append(render_text_run(paragraph[cursor : match.start()]))
        if drawn is None or match.group(1).lower() in drawn:
            parts.append(_figure_ref_text(match.group(1), figure_ref))
        else:
            # The figure is not drawn (missing or unchecked): a numbered
            # reference would print ``??``. The quality report names the gap.
            parts.append(latex_escape(figure_ref) + "~" + latex_escape(match.group(1)))
        cursor = match.end()
    parts.append(render_text_run(paragraph[cursor:]))
    return "".join(parts)


def _pure_inline_formula(original: str, rendered: str) -> bool:
    if re.search(r"\\\(|\\\[|(?<!\\)\$", original):
        return False
    return re.fullmatch(r"\\\(.+\\\)", rendered.strip(), flags=re.DOTALL) is not None


def _explicit_spans(text: str) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    index = 0
    code = {r.start: r for r in code_regions(text)}
    while index < len(text):
        region = code.get(index)
        if region is not None:
            spans.append((region.start, region.end, _inline_code(region.body)))
            index = region.end
            continue
        found = _match_explicit(text, index)
        if found is None:
            index += 1
            continue
        spans.append(found)
        index = found[1]
    return spans


def _match_explicit(text: str, index: int) -> tuple[int, int, str] | None:
    if text.startswith("\\(", index):
        close = text.find("\\)", index + 2)
        if close != -1:
            inner = _math_chars(text[index + 2 : close])
            return index, close + 2, "\\(" + inner + "\\)"
    if text.startswith("\\[", index):
        close = text.find("\\]", index + 2)
        if close != -1:
            inner = _math_chars(text[index + 2 : close]).strip()
            return index, close + 2, "\\[\n" + inner + "\n\\]"
    if text.startswith("$$", index):
        close = text.find("$$", index + 2)
        if close != -1:
            inner = _math_chars(text[index + 2 : close]).strip()
            return index, close + 2, "\\[\n" + inner + "\n\\]"
    if text[index] == "`":
        close = text.find("`", index + 1)
        if close > index + 1 and "\n" not in text[index + 1 : close]:
            return index, close + 1, _inline_code(text[index + 1 : close])
    if text[index] == "$" and not text.startswith("$$", index):
        close = text.find("$", index + 1)
        if close != -1 and _dollar_ok(text[index + 1 : close]):
            inner = _math_chars(text[index + 1 : close])
            return index, close + 1, "\\(" + inner + "\\)"
    return None


def _dollar_ok(inner: str) -> bool:
    if not inner.strip() or "\n" in inner or len(inner) > 300:
        return False
    # A tightly paired numeric literal is explicit math too. Rejecting it
    # leaves its closing dollar available to swallow a later formula.
    if re.fullmatch(r"[+-]?\d+(?:[.,]\d+)?", inner):
        return True
    # Keep ambiguous price separators ("$5, $10", "$5 $10") literal;
    # "$2L/3$" names a variable and is math.
    if (
        inner.lstrip()[:1].isdigit()
        and "=" not in inner
        and "\\" not in inner
        and "{" not in inner
        and "}" not in inner
        and not re.search(r"[A-Za-z]", inner)
    ):
        return False
    if any(character in _MATH for character in inner) or re.search(r"[=^_\\]", inner):
        return True
    if re.search(r"[A-Za-z]{3,}", inner):
        return False
    return re.fullmatch(r"[A-Za-z0-9 +\-*/().,^_{}<>|']+", inner) is not None and bool(
        re.search(r"[A-Za-z0-9]", inner)
    )


def _math_chars(text: str) -> str:
    return _map_math_run(text)


def _script_content(mapping: dict[str, str], character: str) -> str:
    """The LaTeX payload of a subscript/superscript character, e.g. "^{-}" -> "-"."""

    return mapping[character][2:-1]


_QUANTITY = re.compile(
    r"(?P<number>[+-]?\d+(?:[.,]\d+)?)?[ \u00a0]?"
    r"(?P<unit>(?=[^\d]*[µμ°²³⁻/^])[A-Za-zµμ°Ω][A-Za-zµμ°Ω/·\-⁰¹²³⁴⁵⁶⁷⁸⁹⁻^0-9]*)"
)
_UNIT_SUPERSCRIPTS = {chr(0x2070): "0", "¹": "1", "²": "2", "³": "3", **{chr(0x2070 + i): str(i) for i in range(4, 10)}, "⁻": "-"}


def _quantity_tex(span: str) -> str | None:
    """A measured quantity in prose, ``10 µm`` or ``25 °C``, set as upright units.

    The generic path put ``10 µm`` in math italics with the space lost and cut
    ``1,9 g/cm³`` in two. A number and a unit that is recognisably a unit (it
    has a micro sign, a degree sign, a power or a slash) become one formula.
    """

    match = _QUANTITY.fullmatch(span.strip())
    if match is None:
        return None
    if match.group("number") is None and not re.fullmatch(r"[µμ][A-Za-z]+", match.group("unit")):
        return None
    unit = match.group("unit")
    roman: list[str] = []
    out: list[str] = []

    def flush() -> None:
        if roman:
            out.append(r"\mathrm{" + "".join(roman) + "}")
            roman.clear()

    index = 0
    while index < len(unit):
        character = unit[index]
        if character in "µμ":
            flush()
            out.append(r"\mu ")
            index += 1
        elif character == "°":
            flush()
            out.append(r"{}^{\circ}")
            index += 1
        elif character in _UNIT_SUPERSCRIPTS or character == "^":
            flush()
            run: list[str] = []
            index += 1 if character == "^" else 0
            while index < len(unit) and (unit[index] in _UNIT_SUPERSCRIPTS or unit[index].isdigit() or unit[index] == "-"):
                run.append(_UNIT_SUPERSCRIPTS.get(unit[index], unit[index]))
                index += 1
            out.append("^{" + "".join(run) + "}")
        elif character == "·":
            roman.append(r"\cdot ")
            index += 1
        else:
            roman.append(character)
            index += 1
    flush()
    rendered = "".join(out).replace(r"\mu \mathrm{", r"\mu\mathrm{")
    number = match.group("number")
    if number is not None:
        rendered = number.replace(",", "{,}") + r"\," + rendered
    return "\\(" + rendered + "\\)"


def _formula_tex(span: str) -> str:
    quantity = _quantity_tex(span)
    if quantity is not None:
        return quantity
    return "\\(" + _map_math_run(span, escape=True) + "\\)"


#: ``delta U = ...`` spelled in words is a finite change, written as a Delta.
_SPELLED_DELTA = re.compile(r"\b[Dd]elta (?=[A-Za-z](?:_[A-Za-z0-9]+)? ?=)")

# Unbraced snake_case with multiple underscores is an identifier, not a
# sequence of mathematical scripts. Explicit math delimiters override this.
# Bracketed namespaced editorial keys are literal regardless of script count.
_INTERNAL_IDENTIFIER = re.compile(
    r"\[[A-Za-z0-9][A-Za-z0-9.-]*:[A-Za-z0-9_.:-]+\]"
    r"|\b[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+){2,}\b"
    # A trailing underscore (``A_B_``, a genotype written with blanks) would
    # end a subscript with nothing after it, which LaTeX rejects.
    r"|\b[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)*_(?![A-Za-z0-9{])"
    r"|(?<![A-Za-z0-9_])__[A-Za-z][A-Za-z0-9_]*__(?![A-Za-z0-9_])"
)


def _formula_spans(text: str, blocked: list[tuple[int, int, str]]) -> list[tuple[int, int]]:
    tokens = _tokenize(text)
    if not tokens:
        return []
    include = [False] * len(tokens)

    def blocked_token(token_index: int) -> bool:
        start, end, _kind = tokens[token_index]
        return any(start < stop and end > begin for begin, stop, _tex in blocked)

    def takeable(token_index: int, formula_side: tuple[int, int, str] | None, *, adjacent: bool) -> bool:
        if blocked_token(token_index):
            return False
        start, end, kind = tokens[token_index]
        if kind in {"math", "op", "num"}:
            return True
        if kind != "word":
            return False
        if end - start == 1:
            if adjacent:
                return True
            if (
                formula_side is not None
                and formula_side[2] == "op"
                and text[formula_side[0]] not in ")]}"
            ):
                return True
            return text[start] not in _STOP_LETTERS
        # A multi-letter word is part of the formula when it is bound to a script
        # or brace group (rho_fluido, p_{man}), tightly bound to a binding
        # operator (dv/dy, R*T), or heads an assignment (Fr = ..., Re = ...).
        # A long prose word is left as prose.
        if token_index > 0:
            previous = tokens[token_index - 1]
            if previous[2] == "op" and text[previous[0]] in "_^{":
                return True
        if token_index + 1 < len(tokens):
            following = tokens[token_index + 1]
            if following[2] == "op" and text[following[0]] in "_^{":
                return True
            if following[2] == "math" and (text[following[0]] in _SUBSCRIPTS or text[following[0]] in _SUPERSCRIPTS):
                return True
        if 2 <= end - start <= 4 and text[start].isascii() and text[start].isalpha():
            if token_index > 0:
                previous = tokens[token_index - 1]
                if previous[2] == "op" and text[previous[0]] in "/^*":
                    return True
            following = token_index + 1
            if following < len(tokens) and tokens[following][2] == "op" and text[tokens[following][0]] in "/^*":
                return True
        if end - start == 2 and text[start] not in _STOP_LETTERS:
            following = token_index + 1
            if following < len(tokens) and tokens[following][2] == "space" and _one_space(text, tokens[following]):
                following += 1
            if following < len(tokens) and tokens[following][2] == "op" and text[tokens[following][0]] == "=":
                return True
        return False

    def next_index(current: int, direction: int) -> int | None:
        nxt = current + direction
        if nxt < 0 or nxt >= len(tokens):
            return None
        _start, _end, kind = tokens[nxt]
        if kind == "space":
            if not _one_space(text, tokens[nxt]):
                return None
            beyond = nxt + direction
            if beyond < 0 or beyond >= len(tokens):
                return None
            if takeable(beyond, tokens[current], adjacent=False):
                return beyond
            return None
        if takeable(nxt, tokens[current], adjacent=True):
            return nxt
        return None

    for seed, token in enumerate(tokens):
        if token[2] != "math" or blocked_token(seed):
            continue
        include[seed] = True
        left = seed
        while True:
            nxt = next_index(left, -1)
            if nxt is None:
                break
            for cursor in range(nxt, left + 1):
                include[cursor] = True
            left = nxt
        right = seed
        while True:
            nxt = next_index(right, 1)
            if nxt is None:
                break
            for cursor in range(right, nxt + 1):
                include[cursor] = True
            right = nxt
    spans: list[tuple[int, int]] = []
    index = 0
    while index < len(tokens):
        if not include[index]:
            index += 1
            continue
        start = tokens[index][0]
        end = tokens[index][1]
        cursor = index + 1
        while cursor < len(tokens) and include[cursor]:
            end = tokens[cursor][1]
            cursor += 1
        if any(tokens[item][2] == "math" for item in range(index, cursor)):
            spans.append((start, end))
        index = cursor
    return spans


def _tokenize(text: str) -> list[tuple[int, int, str]]:
    tokens: list[tuple[int, int, str]] = []
    index = 0
    while index < len(text):
        character = text[index]
        if character in _MATH:
            tokens.append((index, index + 1, "math"))
            index += 1
            continue
        if character.isalpha():
            end = index + 1
            while end < len(text) and text[end] not in _MATH and text[end].isalpha():
                end += 1
            tokens.append((index, end, "word"))
            index = end
            continue
        if character.isdigit():
            end = index + 1
            while end < len(text) and text[end].isdigit():
                end += 1
            if end < len(text) and text[end] == "." and end + 1 < len(text) and text[end + 1].isdigit():
                end += 1
                while end < len(text) and text[end].isdigit():
                    end += 1
            elif end + 1 < len(text) and text[end] == "," and text[end + 1].isdigit():
                # A Spanish decimal comma belongs to its number; "1,2,3" is a list.
                cursor = end + 1
                while cursor < len(text) and text[cursor].isdigit():
                    cursor += 1
                if not (cursor + 1 < len(text) and text[cursor] == "," and text[cursor + 1].isdigit()):
                    end = cursor
            tokens.append((index, end, "num"))
            index = end
            continue
        if character in " \t":
            end = index + 1
            while end < len(text) and text[end] in " \t":
                end += 1
            tokens.append((index, end, "space"))
            index = end
            continue
        if character in "_^" and index + 1 < len(text) and text[index + 1].isascii() and text[index + 1].isalnum():
            end = index + 1
            while end < len(text) and text[end].isascii() and text[end].isalnum():
                end += 1
            tokens.append((index, end, "math"))
            index = end
            continue
        if character in _ASCII_OPERATORS:
            tokens.append((index, index + 1, "op"))
            index += 1
            continue
        tokens.append((index, index + 1, "other"))
        index += 1
    return tokens


def _one_space(text: str, token: tuple[int, int, str]) -> bool:
    start, end, kind = token
    return kind == "space" and end == start + 1 and text[start] == " "


def _split_blocks(text: str) -> list[tuple[str, str, str]]:
    blocks: list[tuple[str, str, str]] = []
    literals = {r.start: r for r in code_regions(text) if r.block}
    buf: list[str] = []
    index = 0

    def flush() -> None:
        if buf:
            blocks.append(("text", "".join(buf), ""))
            buf.clear()

    while index < len(text):
        region = literals.get(index)
        if region is not None:
            flush()
            blocks.append(("code", region.body, region.language))
            index = region.end
            continue
        env = _read_env(text, index)
        if env is not None:
            flush()
            kind, payload, index = env
            blocks.append((kind, payload, ""))
            continue
        if text.startswith("\\[", index):
            close = text.find("\\]", index + 2)
            if close != -1:
                flush()
                inner = _math_chars(text[index + 2 : close]).strip()
                blocks.append(("display", "\\[\n" + inner + "\n\\]", ""))
                index = close + 2
                continue
        if text.startswith("$$", index):
            close = text.find("$$", index + 2)
            if close != -1:
                flush()
                inner = _math_chars(text[index + 2 : close]).strip()
                blocks.append(("display", "\\[\n" + inner + "\n\\]", ""))
                index = close + 2
                continue
        buf.append(text[index])
        index += 1
    flush()
    return blocks


def _line_start(text: str, index: int) -> bool:
    return index == 0 or text[index - 1] == "\n"


def _read_fence(text: str, index: int) -> tuple[str, str, int] | None:
    line_end = text.find("\n", index)
    if line_end == -1:
        line = text[index:]
        line_end = len(text)
    else:
        line = text[index:line_end]
    match = _FENCE_OPEN.match(line)
    if match is None:
        return None
    marker = match.group(1)
    language = match.group(2)
    close_pattern = re.compile(r"^[ ]{0,3}" + re.escape(marker[0]) + "{" + str(len(marker)) + r",}[ \t]*$")
    cursor = line_end + 1
    while cursor <= len(text):
        next_end = text.find("\n", cursor)
        if next_end == -1:
            closing = text[cursor:]
            next_end = len(text)
            newline = 0
        else:
            closing = text[cursor:next_end]
            newline = 1
        if close_pattern.match(closing):
            return text[line_end + 1 : cursor], language, next_end + newline
        if next_end >= len(text):
            break
        cursor = next_end + 1
    return None


def _read_env(text: str, index: int) -> tuple[str, str, int] | None:
    if not text.startswith("\\begin{", index):
        return None
    for name in _PASS_ENVS:
        token = "\\begin{" + name + "}"
        if not text.startswith(token, index):
            continue
        end_token = "\\end{" + name + "}"
        close = text.find(end_token, index + len(token))
        if close == -1:
            return None
        end = close + len(end_token)
        raw = text[index:end]
        return "environment", raw, end
    return None


def _inline_code(code: str) -> str:
    escaped = _texttt(code)
    if len(code) > 14:
        escaped = re.sub(r"(\\_|[./:(-]|,(?= )|\\textless\{\}|\\textgreater\{\})", r"\1\\allowbreak{}", escaped)
    return r"\texttt{" + escaped + "}"


# The T1 Latin Modern typewriter font ligates ``<<``, ``>>`` and ``--`` into
# guillemets and an en dash, and babel's Spanish shorthands turn ``<<``/``>>``
# into quotation marks that also end the ``\texttt`` group. An empty group after
# each character keeps every code character literal.
_LITERAL_LIGATURE_BREAKS = {
    "<": r"\textless{}",
    ">": r"\textgreater{}",
    "-": "-{}",
}


class UnsupportedLiteralCharacter(ValueError):
    """The selected literal font cannot represent the source faithfully."""


def _texttt(code: str) -> str:
    parts: list[str] = []
    for character in code:
        if character in _LATEX:
            parts.append(_LATEX[character])
        elif character in _ACCENTS:
            parts.append(_literal_actual_text(character, "{" + _ACCENTS[character] + "}"))
        elif character in _MATH:
            parts.append(_literal_actual_text(character, r"\ensuremath{" + _MATH[character] + "}"))
        elif ord(character) < 32 and character != "\t":
            continue
        elif ord(character) > 255:
            raise UnsupportedLiteralCharacter(f"Unsupported literal character U+{ord(character):04X}; use a language escape or a supported font")
        elif character in _LITERAL_LIGATURE_BREAKS:
            parts.append(_LITERAL_LIGATURE_BREAKS[character])
        else:
            parts.append(character)
    return "".join(parts)


def _listing_lines(code: str, language: str) -> list[str]:
    body, escape = _listing_body(code)
    options = ["style=studium"]
    kind = language.strip().lower()
    labels = {"console": "Terminal", "terminal": "Terminal", "output": "Output", "error": "Diagnostic", "json": "JSON", "yaml": "YAML", "toml": "TOML"}
    if kind in labels:
        options.append("title={" + labels[kind] + "}")
        if kind in {"console", "terminal"}:
            options.extend(["backgroundcolor=\\color{studiumInk}", "basicstyle=\\ttfamily\\small\\color{white}"])
        elif kind == "error":
            options.append("rulecolor=\\color{red!70!black}")
    mapped = _LISTINGS_LANGUAGE.get(language.strip().lower())
    if mapped:
        options.append("language={" + mapped + "}")
    if escape is not None:
        begin, end = escape
        options.append("escapeinside={" + begin + "}{" + end + "}")
    return [
        r"\begin{lstlisting}[" + ",".join(options) + "]",
        body,
        r"\end{lstlisting}",
    ]


def _listing_body(code: str) -> tuple[str, tuple[str, str] | None]:
    normalized = code.replace("\r\n", "\n").replace("\r", "\n")
    if normalized.endswith("\n"):
        normalized = normalized[:-1]
    needs_escape = any(ord(character) > 127 for character in normalized) or r"\end{lstlisting}" in normalized
    if not needs_escape:
        return normalized, None
    begin, end = _escape_delimiters(normalized)
    parts: list[str] = []
    for character in normalized:
        if character == "\n" or character == "\t" or 32 <= ord(character) < 127:
            parts.append(character)
            continue
        parts.append(begin + _listing_token(character) + end)
    body = "".join(parts).replace(
        r"\end{lstlisting}",
        begin + r"\textbackslash{}end\{lstlisting\}" + end,
    )
    return body, (begin, end)


def _escape_delimiters(code: str) -> tuple[str, str]:
    for begin, end in _ESCAPE_DELIMS:
        if begin not in code and end not in code:
            return begin, end
    index = 0
    while True:
        begin, end = f"(*studium{index}@", f"@studium{index}*)"
        if begin not in code and end not in code:
            return begin, end
        index += 1


def _literal_actual_text(character: str, visual: str) -> str:
    """Preserve literal Unicode when a TeX math glyph uses multiple PDF characters."""
    encoded = character.encode("utf-16-be").hex().upper()
    return r"\BeginAccSupp{method=hex,ActualText=FEFF" + encoded + "}" + visual + r"\EndAccSupp{}"


def _listing_token(character: str) -> str:
    accent = _ACCENTS.get(character)
    if accent is not None:
        return _literal_actual_text(character, "{" + accent + "}")
    mapped = _MATH.get(character)
    if mapped is not None:
        return _literal_actual_text(character, r"\ensuremath{" + mapped + "}")
    raise UnsupportedLiteralCharacter(f"Unsupported literal character U+{ord(character):04X}; use a language escape or a supported font")


def _formula_line(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return ""
    if re.search(r"\\\(|\\\[|\\begin\{", stripped):
        return render_text_run(stripped)
    return _formula_tex(stripped)


def _looks_like_expression(text: str) -> bool:
    for word in re.findall(r"[A-Za-z]+", text):
        if len(word) >= 3 and word.lower() not in _FUNC_WORDS:
            return False
    return bool(re.search(r"[=+\-*/^_\\0-9]", text) or any(character in _MATH for character in text))


_TEMA_PREFIX = re.compile(r"(?i)^(?:tema\s+\d+\s*:\s*)+")
_BOX_LEAD = re.compile(r"^(Consejo|Definición|Definicion|Autoficha)\s*[:.\-—–]?\s*")
_LEAD_KIND = {
    "Consejo": "consejo",
    "Definición": "definition",
    "Definicion": "definition",
    "Autoficha": "self_check",
}
_GENERIC_SECTION = generic_section_titles()


def _require_language(root: Path) -> BookLanguage:
    language = book_language(root)
    if language is None:
        raise ValueError(INVALID_LANGUAGE)
    return language


def _study_plan_lines(
    root: Path,
    unwritten: list[str],
    written_ids: set[str],
    copy: dict[str, str],
    language: BookLanguage | None = None,
) -> list[str]:
    """Study plan appendix: academic blueprint structure + progress when available."""
    blueprint = current_academic_blueprint(root)
    if blueprint is None:
        if not unwritten:
            return ["", r"\noindent " + latex_escape(copy["empty"])]
        lines: list[str] = []
        for title in unwritten:
            lines.extend(["", r"\noindent " + latex_escape(f"{title}: {copy['unwritten']}")])
        return lines

    lines = []
    parts = blueprint.get("parts")
    if not isinstance(parts, list):
        return ["", r"\noindent " + latex_escape(copy["empty"])]

    for part in parts:
        if not isinstance(part, dict):
            continue
        part_title = _str_field(part, "title")
        lines.extend(["", r"\section*{" + latex_escape(part_title) + "}"])
        part_objectives = part.get("learning_objectives")
        if isinstance(part_objectives, list) and part_objectives:
            lines.append(r"\begin{itemize}")
            for obj in part_objectives:
                if isinstance(obj, str):
                    lines.append(r"\item " + latex_escape(obj))
            lines.append(r"\end{itemize}")
        chapters = part.get("chapters")
        if not isinstance(chapters, list):
            continue
        for chapter in chapters:
            if not isinstance(chapter, dict):
                continue
            ch_id = _str_field(chapter, "id")
            ch_title = _str_field(chapter, "title")
            done = ch_id in written_ids
            marker = r"\checkmark" if done else r"$\square$"
            lines.extend(["", r"\subsection*{" + marker + " " + latex_escape(ch_title) + "}"])
            ch_objectives = chapter.get("learning_objectives")
            if isinstance(ch_objectives, list) and ch_objectives:
                lines.append(r"\begin{itemize}")
                for obj in ch_objectives:
                    if isinstance(obj, str):
                        lines.append(r"\item " + latex_escape(obj))
                lines.append(r"\end{itemize}")
            sections = chapter.get("sections")
            if not isinstance(sections, list):
                continue
            concept_count = 0
            for sec in sections:
                if isinstance(sec, dict):
                    concepts = sec.get("concepts")
                    if isinstance(concepts, list):
                        concept_count += len(concepts)
            if concept_count:
                if language is not None and language.babel == "spanish":
                    phrase = "1 concepto planificado." if concept_count == 1 else f"{concept_count} conceptos planificados."
                else:
                    phrase = "1 concept planned." if concept_count == 1 else f"{concept_count} concepts planned."
                lines.append(r"\noindent " + latex_escape(phrase))

    if unwritten:
        lines.extend(["", r"\medskip"])
        for title in unwritten:
            lines.append(r"\noindent " + latex_escape(f"{title}: {copy['unwritten']}"))
    return lines


def _display_title(title: str) -> str:
    """Blueprint title without a repeated ``Tema N:`` prefix."""

    stripped = _TEMA_PREFIX.sub("", title).strip()
    return stripped or title.strip()


def _textbook_packages() -> list[str]:
    """Color, math, listings, and one tcolorbox style per box kind."""

    return [
        r"\usepackage{xcolor}",
        r"\usepackage{amsmath}",
        r"\usepackage{amssymb}",
        r"\usepackage{array}",
        r"\usepackage{longtable}",
        r"\newcounter{studiumfigure}",
        r"\definecolor{studiumInk}{RGB}{28,40,58}",
        r"\definecolor{studiumRule}{RGB}{28,40,58}",
        r"\definecolor{studiumTipBack}{RGB}{232,244,236}",
        r"\definecolor{studiumTipFrame}{RGB}{27,107,58}",
        r"\definecolor{studiumDefBack}{RGB}{232,240,250}",
        r"\definecolor{studiumDefFrame}{RGB}{24,74,130}",
        r"\definecolor{studiumWorkedBack}{RGB}{255,244,230}",
        r"\definecolor{studiumWorkedFrame}{RGB}{138,78,12}",
        r"\definecolor{studiumCheckBack}{RGB}{243,236,248}",
        r"\definecolor{studiumCheckFrame}{RGB}{96,48,130}",
        r"\definecolor{studiumCodeBack}{RGB}{245,245,242}",
        r"\definecolor{studiumCodeRule}{RGB}{48,48,52}",
        r"\usepackage{listings}",
        r"\lstset{defaultdialect=[5.3]Lua}",
        r"\lstdefinelanguage{Rust}{",
        r"  morekeywords={as,async,await,break,const,continue,crate,dyn,else,enum,extern,false,fn,for,if,impl,in,let,loop,match,mod,move,mut,pub,ref,return,self,Self,static,struct,super,trait,true,type,unsafe,use,where,while},",
        r"  sensitive=true,",
        r"  morecomment=[l]{//},",
        r"  morecomment=[s]{/*}{*/},",
        r"  morestring=[b]{" + "\"" + "}",
        r"}",
        r"\lstdefinelanguage{Go}{",
        r"  morekeywords={break,case,chan,const,continue,default,defer,else,fallthrough,for,func,go,goto,if,import,interface,map,package,range,return,select,struct,switch,type,var},",
        r"  sensitive=true,",
        r"  morecomment=[l]{//},",
        r"  morecomment=[s]{/*}{*/},",
        r"  morestring=[b]{" + "\"" + "}",
        r"}",
        r"\lstdefinelanguage{JavaScript}{",
        r"  morekeywords={break,case,catch,class,const,continue,debugger,default,delete,do,else,export,extends,finally,for,function,if,import,in,instanceof,let,new,return,super,switch,this,throw,try,typeof,var,void,while,with,yield},",
        r"  sensitive=true,",
        r"  morecomment=[l]{//},",
        r"  morecomment=[s]{/*}{*/},",
        r"  morestring=[b]{" + "\"" + "},",
        r"  morestring=[b]{'},",
        r"}",
        r"\lstdefinestyle{studium}{",
        r"  basicstyle=\ttfamily\small,",
        r"  columns=fullflexible,",
        r"  keepspaces=true,",
        r"  showstringspaces=false,",
        r"  breaklines=true,",
        r"  breakatwhitespace=false,",
        r"  frame=leftline,",
        r"  framerule=1.15pt,",
        r"  rulecolor=\color{studiumCodeRule},",
        r"  backgroundcolor=\color{studiumCodeBack},",
        r"  xleftmargin=1.15em,",
        r"  framexleftmargin=0.75em,",
        r"  aboveskip=0.9em,",
        r"  belowskip=0.7em,",
        r"  tabsize=4,",
        r"  keywordstyle=\ttfamily\bfseries,",
        r"  commentstyle=\ttfamily\itshape,",
        r"  stringstyle=\ttfamily",
        r"}",
        r"\lstset{style=studium}",
        r"\usepackage[breakable,skins]{tcolorbox}",
        r"\tcbset{",
        r"  studiumtip/.style={colback=studiumTipBack,colframe=studiumTipFrame,colbacktitle=studiumTipFrame,coltitle=white,coltext=black,fonttitle=\bfseries,boxrule=0.65pt,arc=0.7pt,left=1.7mm,right=1.7mm,top=1.3mm,bottom=1.3mm,before skip=10pt,after skip=10pt},",
        r"  studiumdef/.style={colback=studiumDefBack,colframe=studiumDefFrame,colbacktitle=studiumDefFrame,coltitle=white,coltext=black,fonttitle=\bfseries,boxrule=0.65pt,arc=0.7pt,left=1.7mm,right=1.7mm,top=1.3mm,bottom=1.3mm,before skip=10pt,after skip=10pt},",
        r"  studiumworked/.style={colback=studiumWorkedBack,colframe=studiumWorkedFrame,colbacktitle=studiumWorkedFrame,coltitle=white,coltext=black,fonttitle=\bfseries,boxrule=0.65pt,arc=0.7pt,left=1.7mm,right=1.7mm,top=1.3mm,bottom=1.3mm,before skip=10pt,after skip=10pt},",
        r"  studiumcheck/.style={colback=studiumCheckBack,colframe=studiumCheckFrame,colbacktitle=studiumCheckFrame,coltitle=white,coltext=black,fonttitle=\bfseries,boxrule=0.65pt,arc=0.7pt,left=1.7mm,right=1.7mm,top=1.3mm,bottom=1.3mm,before skip=10pt,after skip=10pt}",
        r"}",
    ]


def _preamble(footer: str, language: BookLanguage, copy: dict[str, str], *, tikz: bool = False) -> list[str]:
    """Load babel (polyglossia only when babel has no name) and the book layout."""

    mark = latex_escape(footer)
    lines = [
        r"\documentclass{book}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage{lmodern}",
        r"\usepackage{upquote}",
        r"\usepackage{accsupp}",
    ]
    if language.loader == "polyglossia":
        lines.extend(
            [
                r"\usepackage{polyglossia}",
                r"\setmainlanguage{" + language.babel + "}",
            ]
        )
    else:
        lines.append(r"\usepackage[" + language.babel + "]{babel}")
        lines.append(
            r"\addto\captions"
            + language.babel
            + r"{\renewcommand{\contentsname}{"
            + latex_escape(copy["contents"])
            + "}}"
        )
    if language.babel == "spanish":
        lines.append(r"\AtBeginDocument{\spanishdeactivate{" + "\"~<>}}")
        lines.append(r"\addto\extrasspanish{\spanishdeactivate{" + "\"~<>}}")
    if language.babel == "galician":
        lines.append(r"\makeatletter\AtBeginDocument{\def\gl@roman#1{\romannumeral#1}}\makeatother")
    lines.extend(
        [
            r"\usepackage[a4paper,margin=2.5cm]{geometry}",
            r"\usepackage{titlesec}",
            r"\titleformat{\chapter}[display]",
            r"  {\normalfont\filright}{\large\scshape\chaptertitlename\ \thechapter}{1ex}{\huge\bfseries}",
            r"\titlespacing*{\chapter}{0pt}{2.5ex plus 1ex minus .2ex}{2.3ex}",
            r"\titleformat{name=\chapter,numberless}[display]",
            r"  {\normalfont\filright}{}{0pt}{\huge\bfseries}",
            r"\titleformat{\section}{\Large\bfseries}{{\thesection}}{0.8em}{}",
            r"\titleformat{\subsection}{\large\bfseries}{{\thesubsection}}{0.7em}{}",
            r"\setcounter{secnumdepth}{3}",
            r"\setcounter{tocdepth}{2}",
            r"\usepackage{graphicx}",
            *( [r"\usepackage{tikz}", r"\usetikzlibrary{arrows.meta,positioning,calc,shapes.geometric}"] if tikz else [] ),
            *_textbook_packages(),
            r"\titleformat{\section}{\Large\bfseries}{\thesection}{0.8em}{}",
            r"\titleformat{\subsection}{\large\bfseries}{\thesubsection}{0.7em}{}",
            r"\setcounter{secnumdepth}{3}",
            r"\setcounter{tocdepth}{2}",
            r"\usepackage{fancyhdr}",
            r"\pagestyle{fancy}",
            r"\fancyhf{}",
            r"\fancyhead[LE]{\small\thepage\hspace{1.5em}\scshape\nouppercase{\leftmark}}",
            r"\fancyhead[RO]{\small\scshape\nouppercase{\rightmark}\hspace{1.5em}\thepage}",
            r"\fancyfoot[C]{\small " + mark + "}",
            r"\renewcommand{\headrulewidth}{0.4pt}",
            r"\renewcommand{\footrulewidth}{0pt}",
            r"\fancypagestyle{plain}{%",
            r"  \fancyhf{}",
            r"  \fancyfoot[C]{\small " + mark + "}",
            r"  \renewcommand{\headrulewidth}{0pt}",
            r"  \renewcommand{\footrulewidth}{0pt}",
            r"}",
            r"\usepackage[hyphens]{url}",
            r"\usepackage[hidelinks]{hyperref}",
            r"\setlength{\emergencystretch}{1.5em}",
            r"\makeatletter",
            r"\@openrightfalse",
            r"\let\cleardoublepage\clearpage",
            r"\makeatother",
        ]
    )
    return lines


def _title_page(root: Path, book: str, copy: dict[str, str]) -> list[str]:
    """Academic draft cover: series, title, subtitle, edition, and date."""

    document = load_project_toml(root)
    edition = document.get("edition")
    edition_text = edition.strip() if isinstance(edition, str) and edition.strip() else "0.1.0"
    course = document.get("course") if isinstance(document.get("course"), dict) else {}
    degree = course.get("degree") if isinstance(course, dict) else None
    university = course.get("university") if isinstance(course, dict) else None
    degree_text = degree.strip() if isinstance(degree, str) else ""
    university_text = university.strip() if isinstance(university, str) else ""
    if degree_text:
        subtitle = degree_text
    elif university_text:
        subtitle = university_text
    else:
        subtitle = copy["subtitle"]
    imprint = university_text if degree_text and university_text else ""
    edition_line = f"{copy['edition']} {edition_text} --- {copy['unreleased']}"
    lines = [
        r"\thispagestyle{empty}",
        r"\setlength{\parindent}{0pt}",
        r"\vspace*{0.08\textheight}",
        r"{\normalsize\scshape\color{studiumInk} Studium\par}",
    ]
    if imprint:
        lines.append(r"{\small " + latex_escape(imprint) + r"\par}")
    lines.extend(
        [
            r"\vspace{0.55em}",
            r"{\color{studiumRule}\rule{\linewidth}{0.9pt}\par}",
            r"\vspace{0.16\textheight}",
            r"{\raggedright\Huge\bfseries " + latex_escape(book) + r"\par}",
            r"\vspace{0.9em}",
            r"{\raggedright\Large\color{studiumInk} " + latex_escape(subtitle) + r"\par}",
            r"\vfill",
            r"{\color{studiumRule}\rule{0.36\linewidth}{0.45pt}\par}",
            r"\vspace{1.05em}",
            r"{\large\scshape " + latex_escape(copy["status"]) + r"\par}",
            r"\vspace{0.45em}",
            r"{\normalsize " + latex_escape(edition_line) + r"\par}",
            r"\vspace{0.4em}",
            r"{\normalsize\today\par}",
            r"\vspace*{0.08\textheight}",
            r"\clearpage",
        ]
    )
    return lines


def _drawn_figure_keys(root: Path) -> frozenset[str]:
    """Keys a render will draw, so a reference never points at a missing label."""

    drawn: set[str] = set()
    for key, record in figure_reference_map(root).items():
        review = _REVIEW_RENDERING.get() and record.get("kind") == "tikz" and isinstance(record.get("source"), str)
        if review or (_checked_output(root, record) is not None and renderable(root, record)):
            drawn.add(key.lower())
    return frozenset(drawn)


def _document(root: Path, *, include_unsupported: bool = False) -> str:
    token = _REVIEW_RENDERING.set(include_unsupported)
    keys_token = _DRAWN_FIGURE_KEYS.set(_drawn_figure_keys(root))
    try:
        return _document_body(root, include_unsupported=include_unsupported)
    finally:
        _DRAWN_FIGURE_KEYS.reset(keys_token)
        _REVIEW_RENDERING.reset(token)


# Profiles whose books are not built on notation or a formula sheet. For them an
# empty appendix is omitted unless the project selects its appendices itself.
_NARRATIVE_PROFILES = frozenset({"HUMANITIES", "SOCIAL_SCIENCES", "LAW", "LIFE_SCIENCES"})


def _render_config(root: Path) -> dict[str, object]:
    config = load_project_toml(root).get("render", {})
    if not isinstance(config, dict):
        raise ValueError("render must be a TOML table")
    return config


def _render_sections(root: Path, key: str, defaults: tuple[str, ...]) -> tuple[str, ...]:
    """Explicit reader editions may select sections without changing authoring data."""
    config = _render_config(root)
    sections = config.get(key, list(defaults))
    if not isinstance(sections, list) or any(not isinstance(s, str) or s not in defaults for s in sections):
        raise ValueError(f"render.{key} must be a list drawn from {defaults}")
    if len(set(sections)) != len(sections):
        raise ValueError(f"render.{key} cannot contain duplicate sections")
    return tuple(sections)


def _document_body(root: Path, *, include_unsupported: bool = False) -> str:
    kind = book_kind(root)
    frontmatter = _render_sections(root, "frontmatter", ("preface", "reader_guide"))
    appendices = _render_sections(root, "appendices", ("notation", "formulas", "solutions", "diagram_report", "audit", "study"))
    language = _require_language(root)
    copy = messages(language)
    if not exercises.numeric_allowed(_domain_profile(root)):
        # A history or law book has no problem to solve; its chapters close with a worked exercise.
        copy = {
            key: value.replace("un problema resuelto", "un ejercicio resuelto")
            .replace("el problema resuelto", "el ejercicio resuelto")
            .replace("a worked problem", "a worked exercise")
            .replace("the worked problem", "the worked exercise")
            for key, value in copy.items()
        }
    sections = current_sections(root)
    claims = supported_drafts(root)
    paragraphs = supported_paragraphs(root)
    if include_unsupported:
        paragraphs = [r for r in fold_by_id(root / PARAGRAPHS) if r.get("status") == "draft"]
    titles = _source_titles(root)
    sources = _source_records(root)
    excerpts = excerpts_by_id(root)
    counts = bibliography_counts(root)
    book = _book_name(root)
    by_section: dict[str, list[dict[str, object]]] = {}
    for paragraph in paragraphs:
        section = paragraph.get("section")
        if isinstance(section, str):
            by_section.setdefault(section, []).append(paragraph)
    lines = [
        *_preamble(copy["footer"], language, copy, tikz=_checked_tikz(root)),
        *([r"\input{../editorial-config.tex}"] if (root / "editorial-config.tex").is_file() else []),
        r"\begin{document}",
        r"\frontmatter",
        r"\ifdefined\studiumcustomtitle",
        r"\studiumcustomtitle",
        r"\else",
        *_title_page(root, book, copy),
        r"\fi",
    ]
    if "preface" in frontmatter:
        lines.extend([
            r"\chapter{" + latex_escape(copy["preface"]) + "}",
            r"\noindent " + latex_escape(copy["note"]),
        ])
    if include_unsupported:
        # Keep the warning even when a reader edition omits the generic preface.
        # An unnumbered paragraph after the TOC avoids an otherwise empty page.
        warning_text = (
            "REVISIÓN DE FUENTES PENDIENTE. Esta copia incluye borradores sin respaldo suficiente. "
            "Compilar no demuestra la integridad de las fuentes ni la corrección técnica."
            if language.babel == "spanish" else
            "EVIDENCE REVIEW REQUIRED. This review copy includes unsupported drafts. "
            "Compilation does not establish source integrity or technical correctness."
        )
        warning = r"\par\medskip\noindent\textbf{" + latex_escape(warning_text) + "}"
        if "preface" in frontmatter:
            lines.append(warning)
    if "reader_guide" in frontmatter:
        lines.extend([
            r"\chapter{" + latex_escape(copy["how"]) + "}",
            r"\noindent " + latex_escape(copy["how_a"]),
            "",
            r"\noindent " + latex_escape(copy["how_b"]),
        ])
    lines.append(r"\tableofcontents")
    if include_unsupported and "preface" not in frontmatter:
        lines.append(warning)
    lines.append(r"\mainmatter")
    unwritten: list[str] = []
    academic = current_academic_blueprint(root)
    if academic is not None:
        lines.extend(_hierarchical_body(root, academic, by_section, unwritten, copy, language))
    else:
        lines.append(r"\part{" + latex_escape(book) + "}")
        if not sections:
            lines.extend(
                [
                    r"\chapter{" + latex_escape(copy["blueprint"]) + "}",
                    r"\noindent " + latex_escape(copy["empty"]),
                ]
            )
        for section in sections:
            section_paragraphs = by_section.get(section["id"], [])
            title = _display_title(section["title"])
            if not section_paragraphs:
                unwritten.append(title)
                continue
            lines.extend(["", r"\chapter{" + latex_escape(title) + "}", _label("chap", section["id"])])
            lines.extend(_chapter_lines(root, section["id"], section_paragraphs, copy, language))
    if appendices:
        lines.append(r"\appendix")
    empty_appendix = ["", r"\noindent " + latex_escape(copy["empty"])]
    narrative = _domain_profile(root) in _NARRATIVE_PROFILES
    chosen = "appendices" in _render_config(root)
    for appendix in appendices:
        if appendix == "diagram_report":
            lines.extend(_diagram_report_lines(root, language))
            continue
        body: list[str] = []
        if appendix == "notation":
            body = _notation_lines(root, copy, language)
        elif appendix == "formulas":
            body = _formula_sheet_lines(root, copy)
        elif appendix == "solutions":
            body = _solution_lines(root, copy, language)
        elif appendix == "audit":
            body = _audit_lines(root, paragraphs, claims, titles, excerpts, sources, copy, kind, counts, language)
        elif appendix == "study":
            body = _study_plan_lines(root, unwritten, set(by_section), copy, language)
        # An appendix that only says it has no material is noise in a history,
        # literature or biology book the author did not configure: notation and
        # a formula sheet do not apply, and a plan with nothing unwritten has
        # nothing to plan. Other books keep the empty appendix as a visible gap.
        if narrative and not chosen and body == empty_appendix and appendix in ("notation", "formulas", "study"):
            continue
        lines.append(r"\chapter{" + latex_escape(copy[appendix]) + "}")
        lines.extend(body)
    lines.extend(_figure_credit_lines(root, language))
    lines.extend(
        [
            r"\backmatter",
            r"\begin{thebibliography}{99}",
        ]
    )
    lines.extend(_bibliography_lines(root, copy, language))
    lines.extend([r"\end{thebibliography}", r"\end{document}", ""])
    return "\n".join(lines)


def _hierarchical_body(
    root: Path,
    academic: dict[str, object],
    by_section: dict[str, list[dict[str, object]]],
    unwritten: list[str],
    copy: dict[str, str],
    language: BookLanguage,
) -> list[str]:
    """Render the main body using the academic blueprint hierarchy.

    Parts become \\part{}, chapters become \\chapter{}, and academic sections
    become \\section{} within each chapter.  Paragraphs are distributed across
    sections based on their optional ``subsection`` field; paragraphs without
    one stay in the chapter body before any sections.
    """
    lines: list[str] = []
    parts = academic.get("parts")
    if not isinstance(parts, list) or not parts:
        return lines
    for part in parts:
        if not isinstance(part, dict):
            continue
        part_title = _str_field(part, "title")
        lines.extend(["", r"\part{" + latex_escape(part_title) + "}"])
        chapters = part.get("chapters")
        if not isinstance(chapters, list):
            continue
        for chapter in chapters:
            if not isinstance(chapter, dict):
                continue
            ch_id = _str_field(chapter, "id")
            ch_title = _display_title(_str_field(chapter, "title"))
            chapter_paragraphs = by_section.get(ch_id, [])
            if not chapter_paragraphs:
                unwritten.append(ch_title)
                continue
            lines.extend(["", r"\chapter{" + latex_escape(ch_title) + "}", _label("chap", ch_id)])
            bp_sections = chapter.get("sections")
            if isinstance(bp_sections, list) and bp_sections:
                lines.extend(
                    _hierarchical_chapter(root, ch_id, chapter_paragraphs, bp_sections, copy, language)
                )
            else:
                lines.extend(_chapter_lines(root, ch_id, chapter_paragraphs, copy, language))
    return lines


def _hierarchical_chapter(
    root: Path,
    chapter_id: str,
    paragraphs: list[dict[str, object]],
    bp_sections: list[object],
    copy: dict[str, str],
    language: BookLanguage,
) -> list[str]:
    """Render a chapter with \\section{} headings from the academic blueprint.

    Paragraphs with a ``subsection`` field matching a blueprint section ID are
    placed under that \\section{}.  Remaining paragraphs go into the chapter
    introduction before any sections.
    """
    section_ids: list[str] = []
    section_titles: dict[str, str] = {}
    section_subsections: dict[str, list[dict[str, object]]] = {}
    for sec in bp_sections:
        if not isinstance(sec, dict):
            continue
        sec_id = _str_field(sec, "id")
        if not sec_id:
            continue
        section_ids.append(sec_id)
        section_titles[sec_id] = _str_field(sec, "title")
        subs = sec.get("subsections")
        if isinstance(subs, list):
            section_subsections[sec_id] = [s for s in subs if isinstance(s, dict)]

    assigned: set[int] = set()
    by_subsection: dict[str, list[dict[str, object]]] = {}
    intro_paragraphs: list[dict[str, object]] = []
    for idx, paragraph in enumerate(paragraphs):
        sub = paragraph.get("subsection")
        if isinstance(sub, str) and sub in section_titles:
            by_subsection.setdefault(sub, []).append(paragraph)
            assigned.add(idx)
        elif isinstance(sub, str):
            for sec_id in section_ids:
                for subsec in section_subsections.get(sec_id, []):
                    if _str_field(subsec, "id") == sub:
                        by_subsection.setdefault(sub, []).append(paragraph)
                        assigned.add(idx)
                        break
                if idx in assigned:
                    break

    for idx, paragraph in enumerate(paragraphs):
        if idx not in assigned:
            intro_paragraphs.append(paragraph)

    lines: list[str] = []
    figures_shown: set[str] = set()
    if intro_paragraphs:
        lines.extend(
            _chapter_lines(root, chapter_id, intro_paragraphs, copy, language, figures_shown, chapter_boxes=False)
        )

    for sec_id in section_ids:
        sec_paragraphs = by_subsection.get(sec_id, [])
        title = section_titles[sec_id]
        nested = [
            _str_field(subsec, "id")
            for subsec in section_subsections.get(sec_id, [])
            if by_subsection.get(_str_field(subsec, "id"))
        ]
        if not sec_paragraphs and not nested:
            continue
        lines.extend(["", r"\section{" + latex_escape(title) + "}"])
        if sec_paragraphs:
            lines.extend(
                _chapter_lines(root, chapter_id, sec_paragraphs, copy, language, figures_shown, chapter_boxes=False)
            )
        subsections = section_subsections.get(sec_id, [])
        for subsec in subsections:
            subsec_id = _str_field(subsec, "id")
            subsec_title = _str_field(subsec, "title")
            if not subsec_id or not subsec_title:
                continue
            subsec_paragraphs = by_subsection.get(subsec_id, [])
            if subsec_paragraphs:
                lines.extend(["", r"\subsection{" + latex_escape(subsec_title) + "}"])
                lines.extend(
                    _chapter_lines(
                        root, chapter_id, subsec_paragraphs, copy, language, figures_shown, chapter_boxes=False
                    )
                )
    lines.extend(_chapter_back_matter(root, chapter_id, copy, language))
    return lines


def _chapter_lines(
    root: Path,
    section_id: str,
    paragraphs: list[dict[str, object]],
    copy: dict[str, str],
    language: BookLanguage,
    figures_shown: set[str] | None = None,
    chapter_boxes: bool = True,
) -> list[str]:
    """Lead and explanation stay in the body. Only four kinds are boxes.

    ``chapter_boxes`` is False when the caller renders the chapter's derivation,
    worked problem and practice set once at the end of the chapter instead of
    after every academic section. Those records are keyed by chapter, so a
    caller that renders several sections would otherwise repeat them.
    """

    if figures_shown is None:
        figures_shown = set()
    purpose: list[tuple[dict[str, object], str]] = []
    consejo: list[tuple[dict[str, object], str]] = []
    definitions: list[tuple[dict[str, object], str]] = []
    self_check: list[tuple[dict[str, object], str]] = []
    body: list[tuple[dict[str, object], str]] = []
    for record in paragraphs:
        role = record.get("role")
        raw = _str_field(record, "text")
        if not raw.strip():
            continue
        label, rest = _split_box_lead(raw) if language.babel == "spanish" else (None, raw)
        kind = _box_kind(role, label, language)
        if kind == "consejo":
            consejo.append((record, _box_body(raw, label, rest, kind, language)))
        elif kind == "definition":
            definitions.append((record, _box_body(raw, label, rest, kind, language)))
        elif kind == "self_check":
            self_check.append((record, _box_body(raw, label, rest, kind, language)))
        elif role == "purpose":
            purpose.append((record, raw))
        else:
            body.append((record, raw))
    lines: list[str] = []
    figure_ref = copy.get("figure_ref", "")
    lines.extend(_record_prose(purpose, figure_ref, italic=True))
    # A figure the lead cites belongs right after the lead, not at the end of the chapter.
    lines.extend(
        _figure_lines(
            root, section_id, copy, figures_shown, keys=[key for record, _ in purpose for key in _cited_keys(_str_field(record, "text"))]
        )
    )
    lines.extend(_body_lines(root, section_id, body, copy, figures_shown))
    lines.extend(_box(copy["consejo"], _record_prose(consejo, figure_ref), "consejo"))
    for record, text in definitions:
        lines.extend(_box(copy["definition"], record_lines(record, _plain([text], figure_ref)), "definition"))
    boxed_keys = [key for _, text in (*consejo, *definitions, *self_check) for key in _cited_keys(text)]
    lines.extend(_figure_lines(root, section_id, copy, figures_shown, keys=boxed_keys))
    if chapter_boxes:
        lines.extend(_chapter_back_matter(root, section_id, copy, language))
    lines.extend(_box(copy["self_check"], _record_prose(self_check, figure_ref), "self_check"))
    # A figure may first be cited in purpose, definition, or self-check prose.
    for record in paragraphs:
        lines.extend(_figure_lines(root, section_id, copy, figures_shown, keys=_cited_keys(_str_field(record, "text"))))
    return lines


def _chapter_back_matter(root: Path, chapter_id: str, copy: dict[str, str], language: BookLanguage) -> list[str]:
    """The chapter's derivation, worked problem and practice set, in order.

    They are stored once per chapter, so they belong once at the end of the
    chapter rather than once after each of its academic sections.
    """

    lines: list[str] = []
    lines.extend(_derivation_box(root, chapter_id, language))
    lines.extend(_worked_box(root, chapter_id, copy, language))
    lines.extend(_exercise_box(root, chapter_id, language))
    return lines


def _body_lines(
    root: Path,
    section_id: str,
    body: list[tuple[dict[str, object], str]],
    copy: dict[str, str],
    figures_shown: set[str] | None = None,
) -> list[str]:
    """Consecutive explanation paragraphs are one body. A new section uses the paragraph's own title."""

    lines: list[str] = []
    placed = False
    figure_ref = copy.get("figure_ref", "")
    for record, raw in body:
        lines.extend(record_lines(record, _body_record_lines(raw, figure_ref)))
        value = raw
        # A cited figure follows the first paragraph that cites it; the rest follow the first paragraph.
        lines.extend(_figure_lines(root, section_id, copy, figures_shown, keys=_cited_keys(value)))
        if not placed:
            lines.extend(_figure_lines(root, section_id, copy, figures_shown, uncited=True))
            placed = True
    if not placed:
        lines.extend(_figure_lines(root, section_id, copy, figures_shown, uncited=True))
    return lines


def _body_record_lines(text: str, figure_ref: str) -> list[str]:
    lines: list[str] = []
    for kind, value in _body_chunks([text]):
        if kind == 'section':
            lines.extend(['', r'\section{' + latex_escape(value) + '}'])
        else:
            lines.extend(_plain([value], figure_ref))
    return lines


def _record_prose(chunks: list[tuple[dict[str, object], str]], figure_ref: str, *, italic: bool = False) -> list[str]:
    lines: list[str] = []
    for record, text in chunks:
        emitted = _italic([text], figure_ref) if italic else _plain([text], figure_ref)
        lines.extend(record_lines(record, emitted))
    return lines


def _cited_keys(text: str) -> list[str]:
    return [match.group(1).lower() for match in FIGURE_REF.finditer(text)]


def _body_chunks(body: list[str]) -> list[tuple[str, str]]:
    chunks: list[tuple[str, str]] = []
    for text in body:
        title, rest = _heading_from_paragraph(text)
        if title is not None:
            chunks.append(("section", title))
        if rest.strip():
            chunks.append(("text", rest))
    return chunks


def _heading_from_paragraph(text: str) -> tuple[str | None, str]:
    """A title is the paragraph's own first line. The word Explicación is not a title."""

    if "\n" not in text:
        return None, text
    first, rest = text.split("\n", 1)
    if any(region.start < len(first) for region in code_regions(text)):
        # Fences and inline code are opaque source, never implicit headings.
        return None, text
    title = first.strip()
    body = rest.strip()
    if not title or not body or len(title) > 80 or title[-1] in ".!?":
        return None, text
    if title.casefold() in _GENERIC_SECTION:
        return None, body
    # Short mathematical lead-ins are body prose, not implicit headings. Do
    # not escape their delimiters into a title and destroy the following math.
    if title[-1] in ",:;" or re.search(r"[\\$=<>≤≥]", title):
        return None, text
    return title, body


def _split_box_lead(text: str) -> tuple[str | None, str]:
    stripped = text.strip()
    match = _BOX_LEAD.match(stripped)
    if match is None:
        return None, text
    return match.group(1), stripped[match.end() :].strip()


def _box_kind(role: object, label: str | None, language: BookLanguage) -> str | None:
    if role in {"consejo", "definition", "self_check"}:
        return str(role)
    if language.babel == "spanish" and role != "purpose":
        return _LEAD_KIND.get(label or "")
    return None


def _box_body(raw: str, label: str | None, rest: str, kind: str | None, language: BookLanguage) -> str:
    if language.babel != "spanish" or not rest.strip():
        return raw
    if _LEAD_KIND.get(label or "") == kind:
        return rest
    return raw


def _italic(chunks: list[str], figure_ref: str = "") -> list[str]:
    lines: list[str] = []
    for text in chunks:
        emitted = emit_prose(text, italic=True, figure_ref=figure_ref)
        if emitted:
            lines.extend(["", *emitted])
    return lines


def _plain(chunks: list[str], figure_ref: str = "") -> list[str]:
    lines: list[str] = []
    for text in chunks:
        emitted = emit_prose(text, figure_ref=figure_ref)
        if emitted:
            lines.extend(["", *emitted])
    return lines


def _box(title: str, body: list[str], kind: str) -> list[str]:
    if not body:
        return []
    style = _BOX_STYLE.get(kind, "studiumdef")
    holds_listing = any(r"\begin{lstlisting}" in line or r"\begin{verbatim}" in line for line in body)
    if holds_listing:
        # Listings already draw their own frame. A surrounding indivisible
        # box would overflow for source longer than a page.
        return ["", r"\par\medskip\noindent\textbf{" + latex_escape(title) + r"}\par\nobreak", *body]
    breaking = ", breakable"
    return [
        "",
        r"\begin{tcolorbox}[title={" + latex_escape(title) + "}, " + style + breaking + "]",
        *body,
        r"\end{tcolorbox}",
    ]


def _worked_problem_records(root: Path, section_id: str) -> list[dict[str, object]]:
    """Problems that may appear as the chapter's worked problem.

    A Rust test is not the worked problem of a book that is not computer
    science. A practice exercise never becomes the worked problem; it belongs
    to the exercise set.
    """

    profile = _domain_profile(root)
    found: list[dict[str, object]] = []
    for record in fold_by_id(root / PROBLEMS):
        if record.get("section") != section_id:
            continue
        if record.get("kind") in {"rust", "programming"} and profile != "COMPUTER_SCIENCE":
            continue
        if record.get("role") == "practice":
            continue
        found.append(record)
    return found


def _worked_box(root: Path, section_id: str, copy: dict[str, str], language: BookLanguage) -> list[str]:
    """One worked problem per chapter, with the statement, the working, and the answer."""

    problems = _worked_problem_records(root, section_id)
    computations = [
        record
        for record in current_computations(root)
        if record.get("section") == section_id and record.get("status") == "replayed" and record.get("correct") is True
    ]
    if not problems and not computations:
        return []
    discursive = [record for record in problems if record.get("kind") == "discursive"]
    if discursive:
        lines: list[str] = []
        for index, exercise in enumerate(discursive, 1):
            title = _extra_label(language, "worked_exercise" if len(discursive) == 1 else "worked_number")
            if len(discursive) > 1:
                title = f"{_extra_label(language, 'worked_exercise')} {index}"
            body = [
                *_discursive_statement_lines(exercise, language, with_label=True),
                *_discursive_answer_lines(exercise, language),
            ]
            lines.extend(_box(title, body, "worked"))
        return lines
    structured = [record for record in problems if isinstance(record.get("solution"), dict) and record.get("solution")]
    if structured:
        lines: list[str] = []
        for index, problem in enumerate(structured, 1):
            solution = problem["solution"]
            assert isinstance(solution, dict)
            body = _solution_body(problem, solution, copy, language, root=root)
            title = copy["worked"] if len(structured) == 1 else f"{_extra_label(language, 'worked_number')} {index}"
            lines.extend(_box(title, body, "worked"))
        return lines
    problem = problems[0] if problems else {}
    computation = computations[0] if computations else {}
    prompt = _str_field(problem, "prompt")
    expected = _str_field(problem, "expected")
    source = _str_field(problem, "source_text")
    expression = _str_field(computation, "expression")
    result = _computation_result(computation)
    statement = prompt.strip() or expression.strip()
    working = expression.strip() if expression.strip() and expression.strip() != statement else source.strip()
    if not working and expression.strip():
        working = expression.strip()
    answer = result.strip() or expected.strip()
    rust = problem.get("kind") == "rust" and bool(source.strip()) and working == source.strip()
    body = [
        *_labeled(copy["enunciado"], statement, expression=not prompt.strip() and bool(expression.strip())),
        *_labeled(
            copy["resolucion"],
            working,
            expression=bool(expression.strip()) and working == expression.strip(),
            language="rust" if rust else "",
        ),
        *_labeled(copy["respuesta"], answer, expression=bool(result.strip()) and answer == result.strip()),
    ]
    return _box(copy["worked"], body, "worked")


def _quote_lines(source: dict[str, object], language: BookLanguage) -> list[str]:
    """The passage a commentary exercise asks the reader to comment, with its attribution."""

    raw = str(source.get("quote") or "").strip()
    verses = [latex_escape(" ".join(line.split())) for line in raw.replace("\r", "").split("\n") if line.strip()]
    if not verses:
        return []
    lines = ["", r"\begin{quote}", r"\itshape " + r" \\ ".join(verses), r"\end{quote}"]
    parts = [str(source.get(key) or "").strip() for key in ("author", "work", "date")]
    credit = ", ".join(latex_escape(part) for part in parts if part)
    if credit:
        lines.extend([r"{\noindent\footnotesize " + credit + r".\par}"])
    note = str(source.get("note") or "").strip()
    if note:
        lines.extend([r"{\noindent\footnotesize " + latex_escape(note) + r"\par}"])
    return lines


def _discursive_statement_lines(record: dict[str, object], language: BookLanguage, *, with_label: bool = False) -> list[str]:
    """Statement, quoted text and guiding questions of a discursive exercise."""

    lines: list[str] = []
    prompt = _str_field(record, "prompt").strip()
    if with_label:
        lines.extend(_labeled(_extra_label(language, "statement"), prompt))
    elif prompt:
        lines.extend(emit_prose(prompt))
    source = record.get("source")
    if isinstance(source, dict):
        if with_label:
            lines.extend(["", r"\noindent\textbf{" + latex_escape(_extra_label(language, "source_text")) + "}"])
        lines.extend(_quote_lines(source, language))
    questions = record.get("questions")
    if isinstance(questions, list) and questions:
        lines.extend(["", r"\noindent\textbf{" + latex_escape(_extra_label(language, "questions")) + r"}", r"\begin{enumerate}"])
        lines.extend(r"\item " + latex_escape(str(item)) for item in questions)
        lines.append(r"\end{enumerate}")
    return lines


def _chronology_lines(events: list[object], language: BookLanguage) -> list[str]:
    rows = sorted((item for item in events if isinstance(item, dict)), key=lambda item: (int(item.get("year") or 0)))
    lines = [
        "",
        r"\noindent\textbf{" + latex_escape(_extra_label(language, "chronology")) + "}",
        r"\begin{itemize}",
    ]
    for row in rows:
        lines.append(r"\item \textbf{" + latex_escape(str(row.get("date") or "")) + r"}. " + latex_escape(str(row.get("text") or "")))
    lines.append(r"\end{itemize}")
    return lines


def _discursive_answer_lines(record: dict[str, object], language: BookLanguage) -> list[str]:
    """The model answer: summary, chronology, labelled points, mistakes and criteria."""

    answer = record.get("answer")
    if not isinstance(answer, dict):
        return []
    lines = ["", r"\noindent\textbf{" + latex_escape(_extra_label(language, "answer_guide")) + "}"]
    summary = answer.get("summary")
    if isinstance(summary, str) and summary.strip():
        lines.extend(emit_prose(summary.strip()))
    events = answer.get("events")
    if isinstance(events, list) and events:
        lines.extend(_chronology_lines(events, language))
    for section in answer.get("sections") or []:
        if not isinstance(section, dict):
            continue
        label = str(section.get("label") or "").strip()
        if label:
            lines.extend(["", r"\noindent\textit{" + latex_escape(label) + "}"])
        lines.append(r"\begin{itemize}")
        for point in section.get("points") or []:
            if isinstance(point, dict) and str(point.get("text") or "").strip():
                lines.append(r"\item " + latex_escape(str(point["text"]).strip()))
        lines.append(r"\end{itemize}")
    for key, label_key in (("mistakes", "mistakes"), ("criteria", "criteria")):
        items = answer.get(key)
        if isinstance(items, list) and items:
            lines.extend(["", r"\noindent\textbf{" + latex_escape(_extra_label(language, label_key)) + r"}", r"\begin{itemize}"])
            lines.extend(r"\item " + latex_escape(str(item)) for item in items)
            lines.append(r"\end{itemize}")
    return lines


def _solution_body(
    problem: dict[str, object],
    solution: dict[str, object],
    copy: dict[str, str],
    language: BookLanguage,
    *,
    root: Path | None = None,
    skip_stages: tuple[str, ...] = (),
) -> list[str]:
    """A structured engineering solution in reading order.

    Statement and its figure; physical model; free-body diagram; equilibrium
    steps; the laws computed from the problem's structured data; the result;
    the graphical solution; interpretation; a one-paragraph verification
    summary; common mistakes. Diagrams appear at the stage they were recorded
    for. Machine evidence stays out of the student's text.
    """

    staged: dict[str, list[dict[str, object]]] = {}
    identifier = problem.get("id")
    if root is not None and isinstance(identifier, str):
        for record in problem_figures(root, identifier):
            block = record.get("diagram")
            stage = block.get("stage") if isinstance(block, dict) else None
            if isinstance(stage, str) and stage not in skip_stages:
                staged.setdefault(stage, []).append(record)

    def figures(stage: str, heading: str | None = None) -> list[str]:
        drawn: list[str] = []
        for record in staged.get(stage, []):
            drawn.extend(_single_figure_lines(root, record, copy) if root is not None else [])
        if drawn and heading:
            drawn = ["", r"\noindent\textbf{" + latex_escape(heading) + "}", *drawn]
        return drawn

    body: list[str] = []
    prompt = _str_field(problem, "prompt")
    if prompt.strip():
        body.extend(_labeled(copy["enunciado"], prompt))
    body.extend(figures("statement"))
    given = solution.get("given")
    if isinstance(given, list):
        body.extend(_given_lines(given, language))
    unknown = solution.get("unknown")
    if isinstance(unknown, str) and unknown.strip():
        body.extend(_labeled(_extra_label(language, "unknown"), unknown))
    model = solution.get("model")
    if isinstance(model, list):
        physical = root is None or _domain_profile(root) == "STEM"
        body.extend(_model_lines(model, language, physical=physical))
    assumptions = solution.get("assumptions")
    if isinstance(assumptions, list):
        body.extend(_bullet_items(_extra_label(language, "assumptions"), [str(item) for item in assumptions], language))
    body.extend(figures("model"))
    body.extend(figures("free_body", _extra_label(language, "free_body")))
    steps = solution.get("steps")
    development = solution.get("development")
    if isinstance(steps, list) and steps:
        if isinstance(development, list) and development:
            body.extend(_numbered_steps([str(item) for item in development], [], language))
        body.extend(_steps_lines(steps, language))
    elif isinstance(development, list) and development:
        body.extend(_numbered_steps([str(item) for item in development], [], language))
    body.extend(figures("equilibrium"))
    structure = problem.get("structure")
    if isinstance(structure, dict) and "laws" not in skip_stages:
        options = DiagramOptions(language=language.tag)
        laws = family_laws(structure.get("family"), structure.get("spec"), options)
        if laws:
            body.extend(["", r"\noindent\textbf{" + latex_escape(_extra_label(language, "laws")) + "}"])
            for block in laws:
                body.extend(_display_math(block))
    body.extend(figures("solution"))
    substitution = solution.get("substitution")
    if isinstance(substitution, str) and substitution.strip():
        body.extend(["", r"\noindent\textbf{" + latex_escape(_extra_label(language, "substitution")) + "}"])
        body.extend(_display_math(substitution))
    result = solution.get("result")
    if isinstance(result, str) and result.strip():
        body.extend(["", r"\noindent\textbf{" + latex_escape(_extra_label(language, "result")) + "}"])
        body.extend(_result_lines(result))
    body.extend(figures("graphical", _extra_label(language, "graphical")))
    interpretation = solution.get("interpretation")
    if isinstance(interpretation, str) and interpretation.strip():
        body.extend(_labeled(_extra_label(language, "interpretation"), interpretation))
    body.extend(figures("interpretation"))
    body.extend(_structure_check_lines(problem, staged, language))
    body.extend(figures("verification"))
    step_checks = problem.get("step_checks")
    if isinstance(step_checks, list):
        body.extend(_step_check_lines(step_checks, language))
    body.extend(_answer_check_lines(problem.get("answer_check"), language))
    limitations = solution.get("limitations")
    if isinstance(limitations, list):
        body.extend(_bullet_items(_extra_label(language, "limitations"), [str(item) for item in limitations], language))
    mistakes = solution.get("mistakes")
    if isinstance(mistakes, list):
        body.extend(_bullet_items(_extra_label(language, "mistakes"), [str(item) for item in mistakes], language))
    return record_lines(problem, body)


def _structure_check_lines(
    problem: dict[str, object], staged: dict[str, list[dict[str, object]]], language: BookLanguage
) -> list[str]:
    """One student-facing sentence saying what the machine checked. Shown only when everything passed."""

    summary = problem.get("structure_check")
    if not isinstance(summary, dict) or summary.get("status") in (None, "verification_failed"):
        return []
    counts = summary.get("counts") if isinstance(summary.get("counts"), dict) else {}
    assert isinstance(counts, dict)
    key = "checks_sentence" if staged else "checks_sentence_plain"
    sentence = _extra_label(language, key).format(
        symbolic=counts.get("symbolic", 0), numeric=counts.get("numeric", 0), dimensional=counts.get("dimensional", 0)
    )
    return _labeled(_extra_label(language, "checks"), sentence)


def _labeled(label: str, text: str, *, expression: bool = False, language: str = "") -> list[str]:
    lines = ["", r"\noindent\textbf{" + latex_escape(label) + "}"]
    if not text.strip():
        return lines
    if language:
        lines.extend(_listing_lines(text, language))
        return lines
    if expression or _looks_like_expression(text):
        lines.extend(["", _formula_line(text)])
        return lines
    lines.extend(emit_prose(text))
    return lines


def _extra_label(language: BookLanguage, key: str) -> str:
    """A box label the language catalog does not carry. Spanish is special-cased."""

    catalog = _EXTRA_BOX_LABELS.get(language.babel, {})
    return catalog.get(key, _EXTRA_BOX_DEFAULTS[key])


def _status_phrase(status: str, language: BookLanguage) -> str:
    """The stored check status in prose. The raw enum name is the fallback."""

    catalog = _STATUS_PHRASES.get(language.babel, {})
    return catalog.get(status, _STATUS_PHRASE_DEFAULTS.get(status, status))


def _practice_records(root: Path, section_id: str) -> list[dict[str, object]]:
    return [
        record
        for record in fold_by_id(root / PROBLEMS)
        if record.get("section") == section_id and record.get("role") == "practice"
    ]


def _practice_numbering(root: Path) -> dict[str, int]:
    """Practice problem id -> its number inside its own chapter."""

    numbering: dict[str, int] = {}
    per_section: dict[str, int] = {}
    for record in fold_by_id(root / PROBLEMS):
        if record.get("role") != "practice":
            continue
        section = str(record.get("section") or "")
        per_section[section] = per_section.get(section, 0) + 1
        identifier = record.get("id")
        if isinstance(identifier, str):
            numbering[identifier] = per_section[section]
    return numbering


def _symbolic_display(symbolic: str) -> list[str]:
    try:
        return _display_math(symbolic_latex(symbolic))
    except MathError:  # pragma: no cover - defensive
        return []


def _named_subscript(name: str) -> str | None:
    """``delta_{11}`` or ``lambda_1``: a Greek word with a subscript, which the symbolic parser cannot read."""

    match = re.fullmatch(r"([A-Za-z]+)_\{?([A-Za-z0-9]+)\}?", name)
    if match is None:
        return None
    base, sub = match.groups()
    tex = DEFAULT_SYMBOL_NAMES.get(base)
    if tex is None:
        return None
    return f"{tex}_{{{DEFAULT_SYMBOL_NAMES.get(sub, sub)}}}"


def _symbol_tex(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        return ""
    try:
        return symbolic_latex(cleaned)
    except MathError:
        pass
    named = _named_subscript(cleaned)
    if named is not None:
        return named
    mapped: list[str] = []
    for ch in cleaned:
        token = _MATH.get(ch)
        if token is not None:
            if mapped and mapped[-1].startswith("\\") and mapped[-1][-1].isalpha() and (token[0].isalpha() or token.startswith("\\")):
                mapped.append(" ")
            mapped.append(token)
        elif ch == "{":
            mapped.append("{")
        elif ch == "}":
            mapped.append("}")
        elif ch == "_":
            mapped.append("_")
        elif ch == "^":
            mapped.append("^")
        else:
            if mapped and mapped[-1].startswith("\\") and mapped[-1][-1].isalpha() and ch.isalpha():
                mapped.append(" ")
            mapped.append(ch)
    return "".join(mapped)


def _unit_tex(unit: str) -> str:
    try:
        return unit_latex(unit)
    except MathError:
        return r"\mathrm{" + latex_escape(unit.strip()) + "}"


def _normalize_math_text(text: str) -> str:
    """Replace Unicode super/subscripts and Greek with ASCII equivalents."""
    _SUPER_MAP = {chr(0x2070 + i): str(i) for i in range(10)}
    _SUPER_MAP.update({"¹": "1", "²": "2", "³": "3"})
    _SUB_MAP = {chr(0x2080 + i): str(i) for i in range(10)}
    out: list[str] = []
    for ch in text:
        if ch in _SUPER_MAP:
            out.append("^" + _SUPER_MAP[ch])
        elif ch in _SUB_MAP:
            out.append("_" + _SUB_MAP[ch])
        elif ch in _GREEK:
            out.append("\\" + _GREEK[ch].lstrip("\\"))
        else:
            out.append(ch)
    return "".join(out)


def _result_lines(text: str) -> list[str]:
    # Results may contain a numerical expression followed by an explanation.
    # Sending an entire explanatory sentence to math mode loses spaces and
    # overflows the page. Explicit math remains handled by emit_prose.
    words = re.findall(r"(?<!\\)\b[^\W\d_]{4,}\b", text)
    if len(words) >= 3 or code_regions(text):
        return emit_prose(text)
    return _display_math(text)


def _display_math(tex: str) -> list[str]:
    lines = _display_math_unaligned(tex)
    if not lines:
        return lines
    display = "\n".join(line for line in lines if line).strip()
    if display.startswith(r"\[") and display.endswith(r"\]"):
        inner = display[2:-2].strip()
        aligned = align_long_chain(inner)
        if aligned != inner:
            return ["", r"\[", aligned, r"\]"]
    return lines


def _display_math_unaligned(tex: str) -> list[str]:
    stripped = tex.strip()
    if not stripped:
        return []
    if stripped.startswith("$$") and stripped.endswith("$$") and len(stripped) > 4:
        return ["", r"\[", _math_chars(stripped[2:-2]), r"\]"]
    if stripped.startswith(r"\[") and stripped.endswith(r"\]"):
        return ["", stripped]
    if stripped.startswith(r"\(") and stripped.endswith(r"\)"):
        return ["", r"\[" + stripped[2:-2] + r"\]"]
    if stripped.startswith("$") and stripped.endswith("$") and len(stripped) > 2:
        return ["", r"\[" + stripped[1:-1] + r"\]"]
    if "\\" not in stripped:
        return ["", r"\[", _formula_tex(stripped)[2:-2], r"\]"]
    return ["", r"\[", stripped, r"\]"]


def _bullet_items(label: str, items: list[str], language: BookLanguage) -> list[str]:
    texts = [item for item in items if isinstance(item, str) and item.strip()]
    if not texts:
        return []
    lines = ["", r"\noindent\textbf{" + latex_escape(label) + "}", r"\begin{itemize}"]
    for text in texts:
        lines.append(r"\item " + _item_run(text, language))
    lines.append(r"\end{itemize}")
    return lines


def _item_run(text: str, _language: BookLanguage) -> str:
    """One list item: explicit math is kept, prose is escaped."""

    return render_text_run(text.strip())


def _numbered_steps(steps: list[str], steps_latex: list[str], language: BookLanguage) -> list[str]:
    count = max(len(steps), len(steps_latex))
    if count == 0:
        return []
    lines = ["", r"\noindent\textbf{" + latex_escape(_extra_label(language, "steps")) + r"}", r"\begin{enumerate}"]
    for index in range(count):
        lines.append(r"\item")
        if index < len(steps) and steps[index].strip():
            lines.extend(emit_prose(steps[index].strip()))
        if index < len(steps_latex) and steps_latex[index].strip():
            lines.extend(_display_math(steps_latex[index]))
    lines.append(r"\end{enumerate}")
    return lines


def _split_trailing_unit(text: str) -> tuple[str, str]:
    """Split "meaning (unit)" into meaning and unit, tolerating nested parentheses."""

    stripped = text.rstrip()
    if not stripped.endswith(")"):
        return text, ""
    depth = 0
    for index in range(len(stripped) - 1, -1, -1):
        char = stripped[index]
        if char == ")":
            depth += 1
        elif char == "(":
            depth -= 1
            if depth == 0:
                prefix = stripped[:index].rstrip()
                unit = stripped[index + 1 : -1].strip()
                if prefix and unit:
                    return prefix, unit
                return text, ""
    return text, ""


def _variables_lines(variables: dict[str, object], language: BookLanguage) -> list[str]:
    if not variables:
        return []
    lines = ["", r"\noindent\textbf{" + latex_escape(_extra_label(language, "variables")) + r"}", r"\begin{itemize}"]
    for name, raw in variables.items():
        if isinstance(raw, dict):
            meaning = _str_field(raw, "meaning")
            units = _str_field(raw, "units")
        else:
            meaning = raw if isinstance(raw, str) else ""
            units = ""
        if not units and meaning:
            meaning, units = _split_trailing_unit(meaning)
        item = "$" + _symbol_tex(str(name)) + "$"
        if meaning:
            item += ": " + render_text_run(str(meaning))
        if units:
            item += " ($" + _unit_tex(str(units)) + "$)"
        lines.append(r"\item " + item)
    lines.append(r"\end{itemize}")
    return lines


_SCI_NOTATION = re.compile(r"^([+-]?\d+(?:\.\d*)?)[eE]([+-]?\d+)$")


def _number_tex(value: str) -> str:
    stripped = value.strip()
    match = _SCI_NOTATION.fullmatch(stripped)
    if match:
        mantissa, exp = match.groups()
        exp_int = int(exp)
        return f"{mantissa}\\times 10^{{{exp_int}}}"
    return render_text_run(stripped)


def _given_lines(given: list[object], language: BookLanguage) -> list[str]:
    if not given:
        return []
    lines = ["", r"\noindent\textbf{" + latex_escape(_extra_label(language, "given")) + r"}", r"\begin{itemize}"]
    for raw in given:
        if not isinstance(raw, dict):
            continue
        symbol = _symbol_tex(str(raw.get("symbol") or ""))
        value = str(raw.get("value") or "")
        unit = str(raw.get("unit") or "")
        item = "$" + symbol + r" = " + (_number_tex(value) if _SCI_NOTATION.fullmatch(value.strip()) else latex_escape(value))
        if unit and unit.strip() and unit.strip().lower() not in {"dimensionless", "adimensional", "1"}:
            item += r"\," + _unit_tex(unit)
        item += "$"
        meaning = raw.get("meaning")
        if isinstance(meaning, str) and meaning.strip():
            item += " — " + render_text_run(meaning.strip())
        lines.append(r"\item " + item)
    lines.append(r"\end{itemize}")
    return lines


def _model_lines(model: list[object], language: BookLanguage, *, physical: bool = True) -> list[str]:
    if not model:
        return []
    heading = _extra_label(language, "model" if physical else "model_generic")
    lines = ["", r"\noindent\textbf{" + latex_escape(heading) + "}"]
    for raw in model:
        if not isinstance(raw, dict):
            continue
        name = raw.get("name")
        latex = raw.get("latex")
        if isinstance(name, str) and name.strip():
            lines.extend(["", r"\noindent\textit{" + latex_escape(name.strip()) + "}"])
        if isinstance(latex, str) and latex.strip():
            lines.extend(_display_math(latex))
    return lines


def _steps_lines(steps: list[object], language: BookLanguage) -> list[str]:
    if not steps:
        return []
    lines = ["", r"\noindent\textbf{" + latex_escape(_extra_label(language, "development")) + r"}", r"\begin{enumerate}"]
    for raw in steps:
        if not isinstance(raw, dict):
            continue
        lines.append(r"\item")
        text = raw.get("text")
        if isinstance(text, str) and text.strip():
            lines.extend(emit_prose(text.strip()))
        equation = raw.get("equation")
        symbolic = raw.get("symbolic")
        if isinstance(equation, str) and equation.strip():
            lines.extend(_display_math(equation))
        elif isinstance(symbolic, str) and symbolic.strip():
            rendered = _symbolic_display(symbolic)
            if rendered:
                lines.extend(rendered)
        expression = raw.get("expression")
        if isinstance(expression, str) and expression.strip():
            try:
                numeric = numeric_latex(expression)
                actual = evaluate(expression)
                # Evaluate the printed expression, rather than copying an
                # unchecked expected value. Keep discrepancies visible in the
                # verification section below.
                if actual.denominator == 1:
                    numeric += " = " + _number_tex(str(actual.numerator))
                else:
                    numeric += r" \approx " + _number_tex(f"{float(actual):.8g}")
            except (MathError, ComputationError, OverflowError):
                # Legacy malformed input stays visible for correction.
                lines.extend(_listing_lines(expression, ""))
            else:
                unit = raw.get("unit")
                if isinstance(unit, str) and unit.strip().lower() not in {"", "1", "dimensionless", "adimensional"}:
                    numeric += r"\quad " + _unit_tex(unit)
                lines.extend(_display_math(numeric))
    lines.append(r"\end{enumerate}")
    return lines


def _step_check_lines(step_checks: list[object], language: BookLanguage) -> list[str]:
    usable = [check for check in step_checks if isinstance(check, dict) and "reproduced" in check]
    if not usable:
        return []
    lines = ["", r"\noindent\textbf{" + latex_escape(_extra_label(language, "verification")) + r"}", r"\begin{itemize}"]
    for check in usable:
        index = check.get("index")
        number = str(index + 1) if isinstance(index, int) else "?"
        value = str(check.get("value") or check.get("expected") or "")
        if check.get("reproduced") is True:
            phrase = _extra_label(language, "reproduced")
        elif check.get("precision") == "ambiguous":
            phrase = _extra_label(language, "ambiguous")
        else:
            phrase = _extra_label(language, "not_reproduced")
        item = latex_escape(_extra_label(language, "step_word")) + " " + latex_escape(number)
        if value:
            item += r": $" + _number_tex(value) + "$"
        item += " — " + latex_escape(phrase)
        lines.append(r"\item " + item)
    lines.append(r"\end{itemize}")
    return lines


def _computation_result(record: dict[str, object]) -> str:
    """A replayed result as the author wrote it, never a raw binary fraction."""

    written = record.get("claimed_text")
    if isinstance(written, str) and written.strip() and record.get("status") == "replayed":
        return written.strip()
    raw = _str_field(record, "server_result").strip()
    if not raw:
        return ""
    try:
        value = Fraction(raw)
    except (ValueError, ZeroDivisionError):
        return raw
    if value.denominator == 1:
        return str(value.numerator)
    return f"{float(value):.6g}"


_ANSWER_PHRASES = {
    "replayed": "answer_replayed",
    "mismatch": "answer_mismatch",
    "ambiguous_precision": "answer_ambiguous",
    "not_replayable": "answer_unreplayable",
}


def _answer_check_lines(answer_check: object, language: BookLanguage) -> list[str]:
    """What the stored answer check established, and what it did not."""

    if not isinstance(answer_check, dict):
        return []
    key = _ANSWER_PHRASES.get(str(answer_check.get("result")))
    if key is None:
        return []
    return [
        "",
        r"\noindent\textbf{" + latex_escape(_extra_label(language, "answer_check")) + "} "
        + latex_escape(_extra_label(language, key)),
    ]


def prose_equation_labels(root: Path) -> set[str]:
    """Every ``\\label{eq:...}`` written in the stored prose of the book, as rendered label commands."""

    found: set[str] = set()
    for paragraph in supported_paragraphs(root):
        text = paragraph.get("text")
        if isinstance(text, str):
            for match in _PROSE_EQ_LABEL.finditer(text):
                found.add(_label("eq", match.group(1)))
    return found


_PROSE_EQ_LABEL = re.compile(r"\\label\{eq:([^{}]+)\}")


def _numbered_math(tex: str, label: str) -> list[str]:
    """A numbered display equation that carries ``label`` inside the environment."""

    display = _display_math(tex)
    inner = "\n".join(line for line in display if line)
    if inner.startswith(r"\[") and inner.endswith(r"\]"):
        inner = inner[2:-2].strip()
    return ["", r"\begin{equation}", inner, label, r"\end{equation}"]


def _derivation_box(root: Path, section_id: str, language: BookLanguage) -> list[str]:
    """The recorded derivations of this chapter with their stored check status."""

    records = derivations_for_section(root, section_id)
    if not records:
        return []
    prose_labels = prose_equation_labels(root)
    label = _extra_label(language, "derivations")
    body: list[str] = []
    for record in records:
        name = _str_field(record, "name")
        equation = _str_field(record, "equation")
        equation_id = _str_field(record, "equation_id")
        body.extend(["", r"\noindent\textbf{" + latex_escape(name.strip() or label) + "}"])
        if equation.strip():
            target = _label("eq", equation_id) if equation_id.strip() else ""
            if target and target not in prose_labels:
                # The derivation is the only place this equation is stated: number it, so that an
                # \eqref from the prose resolves to an equation number and not to the section counter.
                body.extend(_numbered_math(equation, target))
            else:
                # The prose already numbers and labels this equation; a second label would be a
                # LaTeX "multiply defined" warning and a hyperlink that may land on the wrong copy.
                body.extend(_display_math(equation))
        for key, label_key in (
            ("assumptions", "assumptions"),
            ("governing_principles", "principles"),
            ("boundary_conditions", "boundaries"),
            ("applicability", "applicability"),
            ("limitations", "limitations"),
        ):
            values = record.get(key)
            if isinstance(values, list):
                body.extend(_bullet_items(_extra_label(language, label_key), [str(item) for item in values], language))
        steps = record.get("steps")
        steps_latex = record.get("steps_latex")
        body.extend(
            _numbered_steps(
                [str(item) for item in steps] if isinstance(steps, list) else [],
                [str(item) for item in steps_latex] if isinstance(steps_latex, list) else [],
                language,
            )
        )
        variables = record.get("variables")
        if isinstance(variables, dict):
            body.extend(_variables_lines(variables, language))
        verification = record.get("verification")
        status = str(verification.get("status")) if isinstance(verification, dict) else "UNVERIFIED"
        body.extend(["", r"{\noindent\footnotesize " + latex_escape(_status_phrase(status, language)) + r".\par}"])
    return _box(label, body, "derivation")


_PROBLEM_TAG_LABELS = {
    "spanish": {
        "FOUNDATIONAL": "Básico", "INTERMEDIATE": "Intermedio", "ADVANCED": "Avanzado",
        "EXAM_LEVEL": "Nivel de examen", "CHALLENGE": "Reto",
        "CONCEPTUAL": "Conceptual", "NUMERICAL": "Numérico", "SYMBOLIC": "Simbólico",
        "PROOF": "Demostración", "DIMENSIONAL": "Análisis dimensional", "MULTI_STEP": "Desarrollo por pasos",
        "DESIGN": "Diseño", "PARAMETER_STUDY": "Estudio de parámetros", "OPTIMIZATION": "Optimización",
        "INTERPRETATION": "Interpretación", "ERROR_IDENTIFICATION": "Identificación de errores",
        "ASSUMPTION_VALIDATION": "Comprobación de hipótesis", "APPLICATION": "Aplicación", "COMPARATIVE": "Comparación",
        "DEVELOPMENT_QUESTION": "Pregunta de desarrollo", "SOURCE_COMMENTARY": "Comentario de fuente",
        "TEXT_COMMENTARY": "Comentario de texto", "LITERARY_ANALYSIS": "Análisis literario",
        "CHRONOLOGY": "Cronología", "CAUSAL_ANALYSIS": "Causas y consecuencias",
        "EXPERIMENT_DESIGN": "Diseño experimental", "DATA_INTERPRETATION": "Interpretación de datos",
        "MECHANISM_EXPLANATION": "Explicación de un mecanismo", "CASE_ANALYSIS": "Análisis de un caso",
    },
    "english": {
        "FOUNDATIONAL": "Foundational", "INTERMEDIATE": "Intermediate", "ADVANCED": "Advanced",
        "EXAM_LEVEL": "Exam level", "CHALLENGE": "Challenge",
        "CONCEPTUAL": "Conceptual", "NUMERICAL": "Numerical", "SYMBOLIC": "Symbolic",
        "PROOF": "Proof", "DIMENSIONAL": "Dimensional analysis", "MULTI_STEP": "Multi-step",
        "DESIGN": "Design", "PARAMETER_STUDY": "Parameter study", "OPTIMIZATION": "Optimization",
        "INTERPRETATION": "Interpretation", "ERROR_IDENTIFICATION": "Error identification",
        "ASSUMPTION_VALIDATION": "Assumption check", "APPLICATION": "Application", "COMPARATIVE": "Comparison",
        "DEVELOPMENT_QUESTION": "Essay question", "SOURCE_COMMENTARY": "Source commentary",
        "TEXT_COMMENTARY": "Text commentary", "LITERARY_ANALYSIS": "Literary analysis",
        "CHRONOLOGY": "Chronology", "CAUSAL_ANALYSIS": "Causes and consequences",
        "EXPERIMENT_DESIGN": "Experimental design", "DATA_INTERPRETATION": "Data interpretation",
        "MECHANISM_EXPLANATION": "Explaining a mechanism", "CASE_ANALYSIS": "Case analysis",
    },
}


def _problem_tag(tag: str, language: BookLanguage) -> str:
    """Translate display labels only, with the existing English chrome fallback."""
    catalog = _PROBLEM_TAG_LABELS.get(language.babel, _PROBLEM_TAG_LABELS["english"])
    return catalog.get(tag, tag)


def _exercise_box(root: Path, section_id: str, language: BookLanguage) -> list[str]:
    """The practice set of this chapter. Solutions live in the appendix."""

    records = _practice_records(root, section_id)
    if not records:
        return []
    label = _extra_label(language, "exercises")
    body: list[str] = []
    for index, record in enumerate(records, 1):
        prompt = _str_field(record, "prompt")
        difficulty = _str_field(record, "difficulty")
        problem_type = _str_field(record, "problem_type")
        tags = [_problem_tag(tag, language) for tag in (difficulty.strip(), problem_type.strip()) if tag]
        identifier = record.get("id")
        head = f"{index} [{identifier}]" if isinstance(identifier, str) else str(index)
        if tags:
            head += " (" + ", ".join(tags) + ")"
        body.extend(["", r"\noindent\textbf{" + latex_escape(head) + "}"])
        if record.get("kind") == "discursive":
            body.extend(_discursive_statement_lines(record, language))
        elif prompt.strip():
            body.extend(emit_prose(prompt.strip()))
        identifier = record.get("id")
        if isinstance(identifier, str):
            for figure in problem_figures(root, identifier):
                block = figure.get("diagram")
                if isinstance(block, dict) and block.get("stage") == "statement":
                    body.extend(_single_figure_lines(root, figure, messages(language)))
    if any(record.get("kind") == "programming" for record in records):
        # Code banks must flow across pages, without trapping listings in an
        # indivisible box. Solutions remain in the selected appendix.
        return ["", r"\section*{" + latex_escape(label) + "}", *body]
    return _box(label, body, "exercise")


def _figure_lines(
    root: Path,
    section_id: str,
    copy: dict[str, str],
    shown: set[str] | None = None,
    *,
    keys: list[str] | None = None,
    uncited: bool = False,
) -> list[str]:
    """Checked drawings inline. No float, so a short drawing does not take a page.

    Each drawn figure advances ``studiumfigure`` and carries ``\\label{fig:key}``
    (the author's stable key, or the figure id when none was given). A
    ``{{fig:key}}`` reference in the prose therefore resolves to the same
    number without the author maintaining it.

    ``shown`` carries the figure ids already emitted for this chapter. A chapter
    with academic sections calls :func:`_chapter_lines` once per section, but its
    figures are stored per chapter, so without this set every section would
    repeat the same drawings.

    ``keys`` keeps only the figures cited by those keys, in citation order;
    ``uncited`` keeps only figures that no paragraph of the book cites.
    """

    lines: list[str] = []
    records = figures_in_section(root, section_id)
    if keys is not None:
        wanted = list(dict.fromkeys(keys))
        records = sorted(
            (record for record in records if _figure_keys(record) & set(wanted)),
            key=lambda record: min(wanted.index(key) for key in _figure_keys(record) & set(wanted)),
        )
    elif uncited:
        cited = {key.lower() for key in referenced_figure_keys(root)}
        records = [record for record in records if not (_figure_keys(record) & cited)]
    for record in records:
        identifier = record.get("id")
        if shown is not None and isinstance(identifier, str) and identifier in shown:
            continue
        block = record.get("diagram")
        if isinstance(block, dict) and isinstance(block.get("problem"), str):
            # A problem's diagram is drawn inside that problem, at its stage.
            continue
        drawn = _single_figure_lines(root, record, copy)
        if not drawn:
            continue
        if shown is not None and isinstance(identifier, str):
            shown.add(identifier)
        lines.extend(drawn)
    return lines


def _figure_keys(record: dict[str, object]) -> set[str]:
    found = set()
    for field in ("key", "id"):
        value = record.get(field)
        if isinstance(value, str) and value.strip():
            found.add(value.strip().lower())
    return found


# ``\centering`` makes ``\\`` fail inside a node that sets no alignment, although
# the same drawing compiles when it is checked on its own.
_TIKZ_LINEBREAK = r"\makeatletter\let\\\@normalcr\makeatother"


def _single_figure_lines(root: Path, record: dict[str, object], copy: dict[str, str]) -> list[str]:
    """One checked drawing with its numbered caption, or nothing.

    A drawing built from structured data renders only while its checks pass
    and the data it was drawn from are current.
    """

    lines: list[str] = []
    output = _checked_output(root, record)
    review_figure = (_REVIEW_RENDERING.get() and record.get("kind") == "tikz"
                     and isinstance(record.get("source"), str))
    if (output is None or not renderable(root, record)) and not review_figure:
        return lines
    if record.get("kind") == "tikz" and isinstance(record.get("source"), str):
        body = "\n".join(
            [
                r"\begin{tikzpicture}",
                str(record["source"]).strip(),
                r"\end{tikzpicture}",
            ]
        )
        fitted = _fit_block(body, consume_box=False)
    else:
        assert output is not None
        fitted = _fit_block(r"\includegraphics{" + output + "}", consume_box=True)
    caption = _str_field(record, "caption")
    if review_figure and (output is None or not renderable(root, record)):
        caption = "DRAFT FIGURE: evidence review pending. " + caption
    prefix = _figure_caption_prefix(record, copy)
    lines.extend(
        [
            "",
            r"\par\vspace{\baselineskip}",
            r"\noindent\begin{minipage}{\linewidth}",
            r"\centering",
        ]
    )
    if record.get("kind") == "tikz":
        lines.append(_TIKZ_LINEBREAK)
    lines.extend(fitted)
    if caption.strip():
        lines.extend([r"\par\nopagebreak", r"{\small " + prefix + render_text_run(caption) + r"\par}"])
    if record.get("kind") == "image":
        # The credit a reuse licence asks to keep goes with the picture itself.
        lines.extend([r"\par\nopagebreak", r"{\footnotesize " + _image_credit_tex(record) + r"\par}"])
    lines.extend(
        [
            r"\end{minipage}",
            r"\par\vspace{\baselineskip}",
        ]
    )
    return record_lines(record, lines)


def _diagram_report_lines(root: Path, language: BookLanguage) -> list[str]:
    """Appendix table: every rendered diagram, its generator and its current status."""

    rows: list[str] = []
    for record in fold_by_id(root / FIGURES):
        if record.get("deleted") is True or not isinstance(record.get("diagram"), dict):
            continue
        block = record["diagram"]
        assert isinstance(block, dict)
        state = diagram_state(root, record)
        counts = state.get("counts") if isinstance(state.get("counts"), dict) else {}
        assert isinstance(counts, dict)
        total = sum(int(value) for value in counts.values() if isinstance(value, int))
        key = record.get("key") if isinstance(record.get("key"), str) else record.get("id")
        reference = r"\ref{fig:" + _figure_label_key(str(key)) + "}"
        status = _extra_label(language, str(state["status"])) if str(state["status"]) in _EXTRA_BOX_DEFAULTS else str(state["status"])
        rows.append(
            reference
            + " & "
            + r"\texttt{" + latex_escape(str(block.get("generator"))) + "}"
            + " & "
            + latex_escape(status)
            + " & "
            + str(total)
            + r" \\"
        )
    if not rows:
        return []
    return [
        r"\chapter{" + latex_escape(_extra_label(language, "diagram_report")) + "}",
        latex_escape(_extra_label(language, "diagram_intro")),
        "",
        r"\begin{longtable}{llll}",
        latex_escape(_extra_label(language, "diagram_figure"))
        + " & "
        + latex_escape(_extra_label(language, "diagram_generator"))
        + " & "
        + latex_escape(_extra_label(language, "diagram_status"))
        + " & "
        + latex_escape(_extra_label(language, "diagram_checks"))
        + r" \\ \hline",
        *rows,
        r"\end{longtable}",
    ]


def _image_credit_tex(record: dict[str, object]) -> str:
    """Author, title, licence and the page the picture was opened from."""

    text = latex_escape(figure_images.credit_line(record))
    address = figure_images.credit_url(record)
    return f"{text}. {_url_tex(address)}" if address else text


def _figure_credit_lines(root: Path, language: BookLanguage) -> list[str]:
    """Unnumbered list of every rendered picture with its full credit and licence."""

    rows: list[str] = []
    for record in fold_by_id(root / FIGURES):
        if record.get("deleted") is True or record.get("kind") != "image":
            continue
        if _checked_output(root, record) is None:
            continue
        key = record.get("key") if isinstance(record.get("key"), str) and record.get("key") else record.get("id")
        meta = record.get("image")
        assert isinstance(meta, dict)
        licence = r"\href{" + str(meta.get("license_url") or "") + "}{" + latex_escape(str(meta.get("license") or "")) + "}"
        rows.append(
            r"\item \textbf{" + latex_escape(_extra_label(language, "diagram_figure")) + "~\\ref{fig:" + _figure_label_key(str(key)) + "}.} "
            + latex_escape(str(meta.get("author") or ""))
            + ", «" + latex_escape(str(meta.get("title") or "")) + "». "
            + licence + ". " + _url_tex(str(meta.get("url") or ""))
        )
    if not rows:
        return []
    return [
        r"\chapter*{" + latex_escape(_extra_label(language, "figure_credits")) + "}",
        r"\addcontentsline{toc}{chapter}{" + latex_escape(_extra_label(language, "figure_credits")) + "}",
        r"\begin{itemize}",
        *rows,
        r"\end{itemize}",
    ]


def _figure_caption_prefix(record: dict[str, object], copy: dict[str, str]) -> str:
    """Advance the figure counter, set the label, and print ``Figura N.``.

    Empty when the record has no usable key, so an old project without keys
    still renders a plain caption.
    """

    key = record.get("key")
    if not isinstance(key, str) or not key.strip():
        identifier = record.get("id")
        key = identifier if isinstance(identifier, str) else ""
    if not key.strip():
        return ""
    label = copy.get("figure_ref", "figura")
    word = latex_escape(label[:1].upper() + label[1:])
    return (
        r"\refstepcounter{studiumfigure}"
        + r"\label{fig:"
        + _figure_label_key(key)
        + r"}"
        + r"\textbf{"
        + word
        + r"~\thestudiumfigure.} "
    )


def _checked_tikz(root: Path) -> bool:
    for record in fold_by_id(root / FIGURES):
        if record.get("kind") == "tikz" and (_checked_output(root, record) is not None or _REVIEW_RENDERING.get()):
            return True
    return False


def _fit_block(body: str, *, consume_box: bool) -> list[str]:
    """Scale down to the line width and 0.38 of the text height. Do not enlarge.

    ``38\\textheight`` overflows a dimension register, so the cap is
    ``\\textheight/100*38``. The comparison divides by 4096 first so the
    product of the two sides fits in a count.
    """

    shipped = r"\box0" if consume_box else body
    return [
        r"\begingroup",
        r"\setbox0=\hbox{" + body + r"}%",
        r"\count0=\ht0",
        r"\advance\count0 by \dp0",
        r"\count2=\wd0",
        r"\count4=\dimexpr\textheight/100*38\relax",
        r"\count6=\linewidth",
        r"\ifnum\count0<1",
        r"\count0=1",
        r"\fi",
        r"\ifnum\count2<1",
        r"\count2=1",
        r"\fi",
        r"\divide\count0 by 4096",
        r"\divide\count2 by 4096",
        r"\divide\count4 by 4096",
        r"\divide\count6 by 4096",
        r"\ifnum\count0<1",
        r"\count0=1",
        r"\fi",
        r"\ifnum\count2<1",
        r"\count2=1",
        r"\fi",
        r"\ifnum\count4<1",
        r"\count4=1",
        r"\fi",
        r"\ifnum\count6<1",
        r"\count6=1",
        r"\fi",
        r"\count8=\count2",
        r"\ifnum\count0>\count4",
        r"\count8=\numexpr\count2*\count4/\count0\relax",
        r"\fi",
        r"\ifnum\count8>\count6",
        r"\resizebox{\linewidth}{!}{" + shipped + r"}%",
        r"\else",
        r"\ifnum\count0>\count4",
        r"\resizebox{!}{\dimexpr\textheight/100*38\relax}{" + shipped + r"}%",
        r"\else",
        # Natural size: ship the box unscaled. \resizebox{\wd0}{!}{\box0} read
        # \wd0 after \box0 had emptied the register and drew a zero-width
        # figure (F37).
        shipped + r"%",
        r"\fi",
        r"\fi",
        r"\endgroup",
    ]


def _checked_output(root: Path, record: dict[str, object]) -> str | None:
    output = checked_figure_output(root, record)
    return "../" + output if output is not None else None


def _audit_label(root: Path, record: dict[str, object]) -> str:
    """One of two_witnesses, replayed check, single excerpt, or unchecked."""

    raw = record.get("excerpts")
    excerpt_ids = [item for item in raw if isinstance(item, str)] if isinstance(raw, list) else []
    if corroboration_for_excerpts(root, excerpt_ids) == "two_witnesses":
        return "two_witnesses"
    section = record.get("section")
    if isinstance(section, str) and _section_has_replay(root, section):
        return "replayed check"
    if excerpt_ids:
        return "single excerpt"
    return "unchecked"


def _section_has_replay(root: Path, section_id: str) -> bool:
    for record in _worked_problem_records(root, section_id):
        if (
            record.get("kind") == "rust"
            and record.get("status") == "checked"
            and record.get("correct") is True
            and problem_result_current(root, record)
        ):
            return True
    for record in current_computations(root):
        if record.get("section") == section_id and record.get("status") == "replayed" and record.get("correct") is True:
            return True
    return False


def _format_units(raw: str, language: BookLanguage | None = None) -> str:
    """Wrap a plain-text unit string in math-mode ``\\mathrm``."""
    text = raw.strip()
    if not text:
        return ""
    if text.lower() in {"dimensionless", "adimensional", "1"}:
        return "adimensional" if (language is not None and language.babel == "spanish") else "dimensionless"
    if "$" in text or r"\(" in text or r"\mathrm" in text:
        return text
    return "$" + _unit_tex(text) + "$"


def _notation_lines(root: Path, copy: dict[str, str], language: BookLanguage) -> list[str]:
    """The notation appendix from the registry: one row per symbol."""

    registry = notation_registry(root)
    if not registry:
        return ["", r"\noindent " + latex_escape(copy["empty"])]
    symbol_head = latex_escape(_extra_label(language, "symbol"))
    meaning_head = latex_escape(_extra_label(language, "meaning"))
    units_head = latex_escape(_extra_label(language, "units"))
    header = rf"\textbf{{{symbol_head}}} & \textbf{{{meaning_head}}} & \textbf{{{units_head}}} \\"
    # A longtable breaks across pages and repeats its header; a tabular cannot
    # break, so a long registry was drawn off the page (F38). Fixed fractions
    # of the line width keep the columns aligned on every page and wrap long
    # meanings and units instead of overflowing.
    lines = [
        "",
        r"\begingroup",
        r"\setlength{\LTpre}{0pt}",
        r"\setlength{\LTpost}{0pt}",
        r"\begin{longtable}{@{}>{\centering\arraybackslash}p{0.17\linewidth}"
        r">{\raggedright\arraybackslash}p{0.55\linewidth}"
        r">{\raggedright\arraybackslash}p{0.2\linewidth}@{}}",
        header,
        r"\hline",
        r"\endfirsthead",
        header,
        r"\hline",
        r"\endhead",
    ]
    for symbol, entry in sorted(registry.items()):
        meaning = latex_escape(str(entry.get("meaning") or ""))
        units = _format_units(str(entry.get("units") or ""), language)
        sym_tex = _symbol_tex(symbol).replace(",", r",\allowbreak ")
        sym_col = f"${sym_tex}$" if sym_tex else render_text_run(symbol)
        lines.append(rf"{sym_col} & {meaning} & {units} \\")
    lines.extend([r"\end{longtable}", r"\endgroup"])
    return lines


def _formula_sheet_lines(root: Path, copy: dict[str, str]) -> list[str]:
    """The formula sheet from the recorded derivations: name and final equation."""

    records = [
        record
        for record in fold_by_id(root / DERIVATIONS)
        if _str_field(record, "equation").strip()
    ]
    if not records:
        return ["", r"\noindent " + latex_escape(copy["empty"])]
    lines: list[str] = []
    for record in records:
        name = str(record.get("name") or "").strip()
        equation = str(record["equation"]).strip()
        if name:
            lines.extend(["", r"\noindent\textbf{" + latex_escape(name) + "}"])
        lines.extend(_display_math(equation))
    return lines


def _solution_lines(root: Path, copy: dict[str, str], language: BookLanguage) -> list[str]:
    """Checked solutions only. Exercises without a checked solution are named, not invented."""

    groups: dict[str, list[str]] = {}
    profile = _domain_profile(root)
    numbering = _practice_numbering(root)
    seen_practice: set[str] = set()
    solved_practice: set[str] = set()
    exercise_label = _extra_label(language, "exercise")
    for record in fold_by_id(root / PROBLEMS):
        if record.get("kind") == "rust" and profile != "COMPUTER_SCIENCE":
            continue
        identifier = record.get("id")
        is_practice = record.get("role") == "practice"
        if is_practice and isinstance(identifier, str):
            seen_practice.add(identifier)
        current = problem_result_current(root, record)
        checked = (
            current
            and record.get("kind") == "rust"
            and record.get("status") == "checked"
            and record.get("correct") is True
        )
        witnessed = current and (
            record.get("status") == "two_witnesses" or record.get("corroboration") == "two_witnesses"
        )
        review_only = _REVIEW_RENDERING.get() and not checked and not witnessed
        if not checked and not witnessed and not review_only:
            continue
        prompt = _str_field(record, "prompt")
        if not prompt.strip():
            continue
        if record.get("kind") == "discursive" and not is_practice:
            # The worked exercise already carries its model answer in the chapter.
            continue
        section = _str_field(record, "section")
        lines = groups.setdefault(section, [])
        if is_practice and isinstance(identifier, str):
            if not review_only:
                solved_practice.add(identifier)
            number = numbering.get(identifier, 0)
            lines.extend(["", r"\noindent\textbf{" + latex_escape(f"{exercise_label} {number} [{identifier}]") + "}"])
        elif isinstance(identifier, str):
            lines.extend(["", r"\noindent\textbf{" + latex_escape(f"{copy['worked']} [{identifier}]") + "}"])
        solution = record.get("solution")
        if record.get("kind") == "discursive":
            if review_only:
                warning = "Pauta propuesta; verificación pendiente." if language.babel == "spanish" else "Proposed model answer; verification pending."
                lines.extend(["", r"\noindent\textbf{" + warning + "}"])
            if is_practice:
                lines.extend(_discursive_statement_lines(record, language))
            lines.extend(_discursive_answer_lines(record, language))
            continue
        if record.get("kind") == "programming":
            # Behavioral evidence belongs to the external test report. It does
            # not promote an authored solution to academic approval.
            note = "Solución de referencia para revisión; las pruebas cubren los casos indicados, no todos los programas posibles." if language.babel == "spanish" else "Reference solution for review; tests cover only the stated cases."
            lines.extend(["", *emit_prose(note)])
            if isinstance(solution, dict) and isinstance(solution.get("text"), str):
                lines.extend(emit_prose(solution["text"]))
            continue
        if review_only:
            warning = "Solución propuesta; verificación pendiente." if language.babel == "spanish" else "Proposed solution; verification pending."
            lines.extend(["", r"\noindent\textbf{" + warning + "}", "", *emit_prose(prompt)])
            if isinstance(solution, dict) and solution and not is_practice:
                # Worked developments already appear in their chapter. Keep a
                # short answer pointer, not a second copy of the whole solution.
                note = "Desarrollo propuesto en el capítulo correspondiente." if language.babel == "spanish" else "Proposed development appears in the corresponding chapter."
                lines.extend(["", latex_escape(note)])
                result = solution.get("result")
                if isinstance(result, str):
                    lines.extend(_result_lines(result))
            elif isinstance(solution, dict) and solution:
                pending = {key: value for key, value in record.items() if key not in {"step_checks", "answer_check", "structure_check"}}
                lines.extend(_solution_body(pending, solution, copy, language, root=root, skip_stages=("statement",)))
            else:
                expected = _str_field(record, "expected")
                if expected.strip():
                    label = "Respuesta propuesta, sin comprobar" if language.babel == "spanish" else "Proposed answer, not verified"
                    lines.extend(["", r"\noindent\textbf{" + label + "}: " + latex_escape(expected)])
            continue
        if is_practice and isinstance(solution, dict) and solution:
            # A practice problem with a stored solution gets the same full
            # engineering solution the worked problem does, so the appendix is a
            # real solutions manual instead of a bare answer list.
            lines.extend(_solution_body(record, solution, copy, language, root=root, skip_stages=("statement",)))
            continue
        lines.extend(["", *emit_prose(prompt)])
        if witnessed:
            result = solution.get("result") if isinstance(solution, dict) else None
            if isinstance(result, str) and result.strip():
                # A problem with a structured solution already typesets its
                # answer; reuse it so the appendix never prints a raw float.
                lines.extend(["", r"\noindent\textbf{" + latex_escape(copy["respuesta"]) + "}"])
                lines.extend(_result_lines(result))
                lines.extend(_answer_check_lines(record.get("answer_check"), language))
            else:
                expected = _str_field(record, "expected")
                if expected.strip():
                    lines.extend(
                        [
                            "",
                            r"\noindent\textbf{" + latex_escape(copy["respuesta"]) + "} " + latex_escape(expected.strip()),
                        ]
                    )
    computation_sections: set[str] = set()
    for record in current_computations(root):
        if record.get("status") != "replayed" or record.get("correct") is not True:
            continue
        section = _str_field(record, "section")
        lines = groups.setdefault(section, [])
        if section not in computation_sections:
            lines.extend(["", r"\subsection*{" + latex_escape(_extra_label(language, "computations")) + "}"])
            computation_sections.add(section)
        expression = _str_field(record, "expression")
        result = _computation_result(record)
        try:
            expr_tex = numeric_latex(expression)
            res_tex = _number_tex(result) if _SCI_NOTATION.fullmatch(result.strip()) else numeric_latex(result)
            lines.extend(["", rf"\({expr_tex} = {res_tex}\)"])
        except MathError:
            lines.extend(["", _formula_line(f"{expression} = {result}")])
    titles = {section["id"]: section["title"] for section in current_sections(root)}
    academic = current_academic_blueprint(root)
    if academic is not None:
        for part in _iter_list(academic.get("parts")):
            for chapter in _iter_list(part.get("chapters")):
                identifier, title = _str_field(chapter, "id"), _str_field(chapter, "title")
                if identifier and title:
                    titles[identifier] = title
    lines: list[str] = []
    # Follow blueprint order even when records were authored out of order.
    for section in dict.fromkeys([*titles, *groups]):
        if section not in groups:
            continue
        title = titles.get(section, section or _extra_label(language, "unassigned"))
        lines.extend(["", r"\section{" + latex_escape(_display_title(title)) + "}", *groups[section]])
    unsolved = len(seen_practice - solved_practice)
    if unsolved:
        if language.babel == "spanish":
            note = (
                "1 ejercicio todavía sin solución comprobada."
                if unsolved == 1
                else f"{unsolved} ejercicios todavía sin solución comprobada."
            )
        else:
            note = (
                "1 exercise still without a checked solution."
                if unsolved == 1
                else f"{unsolved} exercises still without a checked solution."
            )
        lines.extend(["", r"\noindent\textit{" + latex_escape(note) + "}"])
    if not lines:
        lines.extend(["", r"\noindent " + latex_escape(copy["empty"])])
    return lines


_EQUATION_STATUS_LABELS: dict[str, dict[str, str]] = {
    "spanish": {
        "heading": "Ecuaciones",
        "symbolically_verified": "verificada simbólicamente",
        "dimensionally_verified": "verificada dimensionalmente",
        "numerically_reproduced": "reproducida numéricamente",
        "source_supported": "respaldada por una fuente",
        "follows_from_stated_premises": "se deduce de premisas enunciadas",
        "derived_steps_unchecked": "paso intermedio sin comprobar",
        "numerically_ambiguous": "de precisión numérica ambigua",
        "not_machine_checkable": "no comprobable automáticamente",
        "unsupported": "sin respaldo",
        "contradicted": "contradicha por sus números",
        "verification_failed": "con comprobación fallida",
        "definition": "definición",
        "approximation": "aproximación",
        "value_or_condition": "valor o condición",
    }
}
_EQUATION_STATUS_DEFAULTS = {
    "heading": "Equations",
    "symbolically_verified": "symbolically verified",
    "dimensionally_verified": "dimensionally verified",
    "numerically_reproduced": "numerically reproduced",
    "source_supported": "supported by a source",
    "follows_from_stated_premises": "follows from stated premises",
    "derived_steps_unchecked": "unchecked intermediate step",
    "numerically_ambiguous": "of ambiguous numerical precision",
    "not_machine_checkable": "not machine-checkable",
    "unsupported": "unsupported",
    "contradicted": "contradicted by its numbers",
    "verification_failed": "with a failed check",
    "definition": "definition",
    "approximation": "approximation",
    "value_or_condition": "value or condition",
}


def _equation_status_note(
    root: Path, paragraph: dict[str, object], grounding: GroundingContext, language: BookLanguage | None
) -> str:
    """`` Ecuaciones: 2 derivación comprobada, 1 no comprobable automáticamente.`` or empty."""

    counted: dict[str, int] = {}
    for _statement, status in formula_statuses(root, paragraph, grounding):
        counted[status] = counted.get(status, 0) + 1
    if not counted:
        return ""
    labels = _EQUATION_STATUS_LABELS.get(language.babel, {}) if language is not None else {}
    parts = [
        f"{counted[status]} {labels.get(status, _EQUATION_STATUS_DEFAULTS[status])}"
        for status in FORMULA_STATUSES
        if counted.get(status)
    ]
    heading = labels.get("heading", _EQUATION_STATUS_DEFAULTS["heading"])
    return f" {heading}: " + ", ".join(parts) + "."


def _audit_lines(
    root: Path,
    paragraphs: list[dict[str, object]],
    claims: list[dict[str, object]],
    titles: dict[str, str],
    excerpts: dict[str, dict[str, object]],
    sources: dict[str, dict[str, object]],
    copy: dict[str, str],
    kind: str,
    counts: dict[str, int],
    language: BookLanguage | None = None,
) -> list[str]:
    """Source audit grouped by source, with per-paragraph verification status."""

    lines = ["", r"\noindent " + latex_escape(_status_line(kind, counts, copy))]

    # --- per-paragraph verification status (compact) ---
    grounding = GroundingContext(root)
    statuses: list[tuple[str, str]] = []
    for idx, paragraph in enumerate(paragraphs, 1):
        label = _audit_label(root, paragraph)
        visible = _visible_label(copy, label)
        equations = _equation_status_note(root, paragraph, grounding, language)
        statuses.append((f"¶{idx}", f"{visible}.{equations}"))
    for line in _collapse_runs(statuses):
        lines.extend(["", r"\noindent " + latex_escape(line)])

    # --- evidence grouped by source ---
    source_paragraphs: dict[str, list[int]] = {}
    for idx, paragraph in enumerate(paragraphs, 1):
        for eid in _list_field(paragraph, "excerpts"):
            if not isinstance(eid, str):
                continue
            exc = excerpts.get(eid)
            sid = exc.get("source_id") if isinstance(exc, dict) else None
            if isinstance(sid, str):
                source_paragraphs.setdefault(sid, []).append(idx)
        for sid in _list_field(paragraph, "sources"):
            if isinstance(sid, str):
                source_paragraphs.setdefault(sid, []).append(idx)

    if source_paragraphs:
        lines.extend(["", r"\medskip"])
        for sid, par_nums in source_paragraphs.items():
            title = titles.get(sid, sid)
            src = sources.get(sid) if isinstance(sources, dict) else None
            status_parts = [latex_escape(f"{title} (PENDING)")]
            if isinstance(src, dict) and src.get("open_supplement") is True:
                status_parts.append(latex_escape(copy["open_supplement"]))
                if src.get("course_guide_cited") is not True:
                    status_parts.append(latex_escape(copy["not_guide"]))
            refs = ", ".join(f"\\P{n}" for n in sorted(set(par_nums)))
            status_parts.append(refs)
            lines.extend(["", r"\noindent " + " --- ".join(status_parts) + "."])

    # --- leftover claims ---
    for claim in claims:
        identifier = _str_field(claim, "id", "claim")
        label = _audit_label(root, claim)
        lines.extend(["", r"\noindent " + latex_escape(copy["leftover"])])
        lines.extend(["", r"\noindent " + latex_escape(f"{identifier}: {label}")])
        lines.extend(_source_notes(claim, titles, excerpts, sources, copy, include_text=True))

    # --- audits and figures ---
    recorded_audits: list[tuple[str, str]] = []
    for record in fold_by_id(root / AUDITS):
        if record.get("status") != "recorded":
            continue
        identifier = _str_field(record, "id", "audit")
        target = _str_field(record, "target")
        if target.startswith("PAR-"):
            target = ""
        check_kind = _str_field(record, "kind")
        recorded_audits.append((identifier, f"{target} {check_kind}".strip()))
    for line in _collapse_runs(recorded_audits):
        lines.extend(["", r"\noindent " + latex_escape(line)])
    for record in fold_by_id(root / FIGURES):
        identifier = _str_field(record, "id", "figure")
        if _checked_output(root, record) is None:
            lines.extend(["", r"\noindent " + latex_escape(f"{identifier}: {copy['figure_gap']}")])
            continue
        if record.get("caption_corroboration") == "unchecked":
            lines.extend(["", r"\noindent " + latex_escape(f"{identifier}: {copy['caption']}")])
    return lines


_MIN_COLLAPSED_RUN = 4


def _collapse_runs(entries: list[tuple[str, str]]) -> list[str]:
    """``label: status`` lines, with a run of identical statuses as one range.

    A book of eighty paragraphs that all share one status printed eighty
    identical lines in the source audit. A run of ``_MIN_COLLAPSED_RUN`` or more
    consecutive entries prints once as ``first–last: status``.
    """

    lines: list[str] = []
    index = 0
    while index < len(entries):
        end = index
        while end + 1 < len(entries) and entries[end + 1][1] == entries[index][1]:
            end += 1
        if end - index + 1 >= _MIN_COLLAPSED_RUN:
            lines.append(f"{entries[index][0]}–{entries[end][0]}: {entries[index][1]}")
        else:
            lines.extend(f"{label}: {status}" for label, status in entries[index : end + 1])
        index = end + 1
    return lines


def _visible_label(copy: dict[str, str], label: str) -> str:
    return {
        "two_witnesses": copy["two_witnesses"],
        "replayed check": copy["replayed"],
        "single excerpt": copy["single_excerpt"],
        "unchecked": copy["unchecked"],
    }.get(label, label)


_URL_SAFE_CHARACTERS = "%:/?#[]@!$&'()*+,;=-._~"


def _url_tex(url: str) -> str:
    """A clickable, breakable URL. ``\\url`` keeps the raw characters and lets
    TeX break at ``/``, ``.`` and ``-`` so a long address cannot overflow."""

    cleaned = url.strip().replace("\\", "").replace("{", "").replace("}", "").replace("\n", "").replace(" ", "")
    if not cleaned:
        return ""
    if "://" in cleaned or cleaned.startswith("www."):
        # pdfLaTeX cannot typeset non-ASCII characters inside ``\url``; an
        # accented title such as ``Mester_de_clerecía`` printed as mojibake. The
        # percent-encoded form is the same address, readable and copyable.
        return r"\url{" + urllib.parse.quote(cleaned, safe=_URL_SAFE_CHARACTERS) + "}"
    return latex_escape(cleaned)


def _bibliography_lines(root: Path, copy: dict[str, str], language: BookLanguage | None = None) -> list[str]:
    lines: list[str] = []
    index = 0
    for record in fold_by_id(root / PUBLIC_BIBLIOGRAPHY):
        title = _str_field(record, "title")
        url = _str_field(record, "url")
        if not title and not url:
            continue
        index += 1
        origin = _str_field(record, "origin")
        note = " student_notes." if origin == "student_notes" else ""
        parts = [latex_escape(f"{title}.")] if title.strip() else []
        rendered_url = _url_tex(url)
        if rendered_url:
            parts.append(rendered_url)
        if note:
            parts.append(latex_escape(note.strip()))
        lines.append(r"\bibitem{src" + str(index) + "} " + " ".join(parts))
    label = _extra_label(language, "user_material") if language is not None else _EXTRA_BOX_DEFAULTS["user_material"]
    for _source_id, filename in _quoted_local_sources(root):
        index += 1
        lines.append(r"\bibitem{src" + str(index) + "} " + latex_escape(f"{filename}. {label}"))
    if not lines:
        lines.append(r"\bibitem{none} " + latex_escape(copy["empty"]))
    return lines


def _quoted_local_sources(root: Path) -> list[tuple[str, str]]:
    """User-provided sources that a stored excerpt quotes: id and file name, never a path."""

    quoted: list[str] = []
    for excerpt in fold_by_id(root / EXCERPTS):
        source_id = excerpt.get("source_id")
        if excerpt.get("source_kind") == "local" and isinstance(source_id, str) and source_id not in quoted:
            quoted.append(source_id)
    names = {
        str(record.get("id")): str(record.get("filename") or record.get("id"))
        for record in fold_by_id(root / "sources" / "registry.jsonl")
    }
    return [(source_id, names[source_id]) for source_id in quoted if source_id in names]


def _status_line(kind: str, counts: dict[str, int], copy: dict[str, str]) -> str:
    pending = counts.get("pending", 0)
    conflicting = counts.get("conflicting", 0)
    not_cited = counts.get("not_cited", 0)
    guide = copy["guide_topic"] if kind == BOOK_TOPIC else copy["guide_course"]
    return (
        f"{copy['status_head']} "
        f"{pending} {copy['pending_word']}. "
        f"{copy['conflicts'].format(n=conflicting)} "
        f"{guide} "
        f"{copy['not_cited'].format(n=not_cited)}"
    )


def _source_notes(
    record: dict[str, object],
    titles: dict[str, str],
    excerpts: dict[str, dict[str, object]],
    sources: dict[str, dict[str, object]] | None,
    copy: dict[str, str],
    *,
    include_text: bool,
) -> list[str]:
    """Appendix citation lines. Paragraph ids are omitted."""

    lines: list[str] = []
    if include_text:
        text = _str_field(record, "text")
        if text.strip():
            lines.extend(["", *emit_prose(text)])
    cited_sources = _list_field(record, "sources")
    excerpt_ids = _list_field(record, "excerpts")
    labels: list[str] = []
    for source_id in cited_sources:
        if not isinstance(source_id, str):
            continue
        labels.append(f"{titles.get(source_id, source_id)} (PENDING)")
    excerpt_labels: list[str] = []
    for excerpt_id in excerpt_ids:
        if not isinstance(excerpt_id, str):
            continue
        excerpt = excerpts.get(excerpt_id)
        source_id = excerpt.get("source_id") if isinstance(excerpt, dict) else None
        title = titles.get(source_id, source_id) if isinstance(source_id, str) else excerpt_id
        source = sources.get(source_id) if isinstance(sources, dict) and isinstance(source_id, str) else None
        if isinstance(source, dict) and source.get("open_supplement") is True and source.get("course_guide_cited") is not True:
            excerpt_labels.append(
                f"{copy['open_supplement']} {excerpt_id} {title} (PENDING). {copy['not_guide']}"
            )
        else:
            excerpt_labels.append(f"{excerpt_id} {title} (PENDING)")
    source_heading = copy["sources_heading"]
    excerpt_heading = copy["excerpts_heading"]
    if labels:
        lines.extend(["", r"\noindent " + source_heading + ": " + latex_escape(", ".join(labels)) + "."])
    if excerpt_labels:
        lines.extend(["", r"\noindent " + excerpt_heading + ": " + latex_escape(", ".join(excerpt_labels)) + "."])
    return lines


def _source_records(root: Path) -> dict[str, dict[str, object]]:
    records: dict[str, dict[str, object]] = {}
    for record in fold_by_id(root / PUBLIC_BIBLIOGRAPHY):
        identifier = record.get("id")
        if isinstance(identifier, str):
            records[identifier] = record
    return records


def _source_titles(root: Path) -> dict[str, str]:
    titles: dict[str, str] = {}
    for record in fold_by_id(root / PUBLIC_BIBLIOGRAPHY):
        identifier = record.get("id")
        title = record.get("title")
        if isinstance(identifier, str) and isinstance(title, str):
            titles[identifier] = title
    for source_id, filename in _quoted_local_sources(root):
        titles.setdefault(source_id, filename)
    return titles


def _book_name(root: Path) -> str:
    course = load_project_toml(root).get("course")
    if isinstance(course, dict) and isinstance(course.get("name"), str) and course["name"].strip():
        return course["name"].strip()
    return "Draft"


def _outputs(root: Path) -> tuple[Path | None, Path | None]:
    directory = (root / "latex").resolve()
    try:
        directory.relative_to(root.resolve())
    except ValueError:
        return None, None
    tex_path = directory / _TEX_NAME
    pdf_path = directory / _PDF_NAME
    return tex_path, pdf_path


def _remove_stale_toc(tex_path: Path) -> None:
    """Drop the previous contents file so the next compile rebuilds it."""

    toc = tex_path.with_suffix(".toc")
    try:
        if toc.is_symlink() or not toc.is_file():
            return
        toc.unlink()
    except OSError:
        return


def _compile(engine: str, tex_path: Path, out_dir: Path) -> tuple[bool, str]:
    _remove_stale_toc(tex_path)
    tex_path.with_suffix(".compiler.log").write_text("", encoding="utf-8")
    previous_log = tex_path.with_suffix(".log")
    if previous_log.is_file():
        previous_log.replace(tex_path.with_suffix(".previous.log"))
    # pdflatex reads the contents file from the previous pass. The second pass
    # puts the new headings on the contents page. Tectonic repeats internally.
    passes = 1 if Path(engine).name.startswith("tectonic") else 4
    detail = ""
    for pass_index in range(passes):
        compiled, detail = _run_latex(engine, tex_path, out_dir)
        if not compiled:
            return False, detail
        if pass_index >= 1:
            log_path = tex_path.with_suffix(".log")
            log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
            if not re.search(r"Rerun to get|Label\(s\) may have changed|rerunfilecheck Warning", log, re.IGNORECASE):
                break
    return True, ""


def _run_latex(engine: str, tex_path: Path, out_dir: Path) -> tuple[bool, str]:
    name = Path(engine).name
    if name.startswith("tectonic"):
        command = [engine, "--keep-logs", "--keep-intermediates", "--outdir", str(out_dir), str(tex_path)]
    else:
        command = [
            engine,
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-no-shell-escape",
            "-output-directory",
            str(out_dir),
            str(tex_path),
        ]
    try:
        completed = subprocess.run(
            command,
            cwd=out_dir,
            check=False,
            capture_output=True,
            timeout=180,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        partial = exc.stdout if isinstance(exc, subprocess.TimeoutExpired) else None
        output = partial.decode("utf-8", errors="replace") if isinstance(partial, bytes) else str(partial or "")
        with tex_path.with_suffix(".compiler.log").open("a", encoding="utf-8") as stream:
            stream.write(output + "\n" + str(exc) + "\n")
        return False, str(exc)[:400]
    output = completed.stdout.decode("utf-8", errors="replace") + completed.stderr.decode("utf-8", errors="replace")
    with tex_path.with_suffix(".compiler.log").open("a", encoding="utf-8") as stream:
        stream.write(output + "\n")
    if completed.returncode != 0:
        tail = completed.stdout.decode("utf-8", errors="replace")[-400:]
        return False, " ".join(tail.split())
    return True, ""


def _is_pdf(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 5 and path.read_bytes()[:5] == b"%PDF-"
    except OSError:
        return False


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _local(state: dict[str, object]) -> dict[str, object]:
    local = state.get("local_sources")
    if isinstance(local, dict):
        return dict(local)
    return {"status": "UNKNOWN", "prompted": False, "source_count": 0}


def _error(code: str, message: str) -> dict[str, object]:
    return {"status": code, "message": message, "pdf": None, "released": False}
