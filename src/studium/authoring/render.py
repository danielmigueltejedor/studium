"""LaTeX output adapter for a draft. This is not a release build.

Writes ``latex/draft.tex``. Compiles ``latex/draft.pdf`` only when tectonic
or pdflatex is on PATH. A missing engine leaves no PDF behind.
"""

import re
import shutil
import subprocess
from pathlib import Path

from studium.authoring.blueprint import current_sections
from studium.authoring.excerpts import excerpts_by_id
from studium.authoring.figures import figure_gap, figures_in_section
from studium.authoring.paragraphs import GAP_LABEL, supported_paragraphs
from studium.authoring.section_blocks import blocked_ids
from studium.authoring.support import corroboration_for_excerpts, supported_drafts
from studium.domain.profiles import BOOK_TOPIC
from studium.research.public_sources import bibliography_counts
from studium.storage.init_project import book_kind, load_project_toml, load_state_holding_lock
from studium.storage.locking import ProjectLocked, project_lock
from studium.storage.records import AUDITS, COMPUTATIONS, PROBLEMS, PUBLIC_BIBLIOGRAPHY, fold_by_id

_TEX_NAME = "draft.tex"
_PDF_NAME = "draft.pdf"
_EMPTY_PIECE = "Gap: this part of the draft has no stored material yet."
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
_MATH = {**_GREEK, **_SUBSCRIPTS, **_SUPERSCRIPTS}


def render_draft(root: Path) -> dict[str, object]:
    """Write a DRAFT .tex of the blueprint and supported claims, then compile if possible."""

    try:
        with project_lock(root):
            state = load_state_holding_lock(root)
            tex_path, pdf_path = _outputs(root)
            if tex_path is None or pdf_path is None:
                return _error("render.path_escaped", "draft path leaves the project")
            document = _document(root)
            tex_path.parent.mkdir(parents=True, exist_ok=True)
            tex_path.write_text(document, encoding="utf-8")
            _remove_stale_toc(tex_path)
            if pdf_path.exists():
                pdf_path.unlink()
            local = _local(state)
            project_state = state.get("state")
    except ProjectLocked:
        return _error("storage.locked", "project is locked")
    except OSError:
        return _error("render.write_failed", "the .tex draft could not be written")

    engine = find_engine()
    relative_tex = _relative(root, tex_path)
    body = {
        "tex": relative_tex,
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
        return {
            "status": "compiler_missing",
            "message": (
                "no LaTeX engine on PATH (tectonic or pdflatex). "
                "Wrote the .tex draft. No PDF was created."
            ),
            **body,
        }
    compiled, detail = _compile(engine, tex_path, tex_path.parent)
    if compiled and _is_pdf(pdf_path):
        body["pdf"] = _relative(root, pdf_path)
        return {"status": "rendered", "message": "compiled a DRAFT PDF", **body}
    if pdf_path.exists():
        pdf_path.unlink()
    message = "the LaTeX engine failed. Wrote the .tex draft. No PDF was created."
    if detail:
        message = f"{message} {detail}"
    return {"status": "render.compile_failed", "message": message, **body}


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
            parts.append(r"\(" + "".join(math) + r"\)")
            math.clear()

    for character in value:
        token = _MATH.get(character)
        if token is not None:
            math.append(token)
            continue
        flush_math()
        replacement = _LATEX.get(character)
        if replacement is not None:
            parts.append(replacement)
        elif ord(character) < 32 and character not in "\n\t":
            continue
        elif ord(character) > 255:
            parts.append(f"{{U+{ord(character):04X}}}")
        else:
            parts.append(character)
    flush_math()
    return "".join(parts)


_TEMA_PREFIX = re.compile(r"(?i)^(?:tema\s+\d+\s*:\s*)+")
_SPANISH_MARK = re.compile(
    r"[ÁÉÍÓÚÜÑáéíóúüñ¿¡]"
    r"|\b(?:el|la|los|las|del|una|unos|unas|para|como|esta|este|estos|estas|que|también|más|sección|capítulo|fluidos|ecuación|presión|cuando|donde|porque|desde|hasta)\b",
    re.IGNORECASE,
)


def _language(root: Path) -> str:
    """Book language. A missing language with Spanish prose is es."""

    course = load_project_toml(root).get("course")
    if isinstance(course, dict) and isinstance(course.get("language"), str):
        stored = course["language"].strip().lower()
        if stored:
            return stored
    if _prose_is_spanish(root):
        return "es"
    return ""


def _prose_is_spanish(root: Path) -> bool:
    """True when blueprint titles or draft prose are Spanish.

    The course name is not enough: a Spanish course title can still hold English paragraphs.
    """

    chunks: list[str] = []
    for section in current_sections(root):
        title = section.get("title")
        if isinstance(title, str):
            chunks.append(title)
    for paragraph in supported_paragraphs(root):
        text = paragraph.get("text")
        if isinstance(text, str):
            chunks.append(text)
    for claim in supported_drafts(root):
        text = claim.get("text")
        if isinstance(text, str):
            chunks.append(text)
    for record in fold_by_id(root / PROBLEMS):
        prompt = record.get("prompt")
        if isinstance(prompt, str):
            chunks.append(prompt)
    return _SPANISH_MARK.search("\n".join(chunks)) is not None


def _copy(language: str) -> dict[str, str]:
    """Generated headings. Spanish when the book language is es."""

    if language == "es":
        return {
            "preface": "Prefacio",
            "how": "Cómo usar este libro",
            "audit": "Auditoría de fuentes",
            "study": "Plan de estudio",
            "notation": "Notación",
            "formulas": "Hoja de fórmulas",
            "solutions": "Soluciones",
            "blueprint": "Esquema",
            "footer": "Borrador",
            "gap": "Esta sección está vacía.",
            "empty": "Esta parte del borrador aún no tiene material.",
            "blocked": "Bloqueado: no hay un segundo extracto abierto independiente ni una comprobación rehecha.",
            "purpose": "Consejo",
            "explanation": "Definición",
            "worked": "Problema resuelto",
            "self_check": "Autoficha",
            "figure_gap": "Esta figura no está comprobada. El dibujo se omite.",
            "science": "Una figura no demuestra la ciencia.",
            "caption": "La cifra del pie sigue sin comprobar.",
            "leftover": "Borrador antiguo.",
            "note": "Este archivo es un borrador. No está publicado.",
            "how_a": "Una sección puede contener varios párrafos. Cada párrafo sustantivo cita un extracto almacenado.",
            "how_b": "Un capítulo lleva una entrada en cursiva, la explicación en el cuerpo, como mucho un consejo, definiciones solo al introducir un término, un problema resuelto y una autoficha.",
            "consejo": "Consejo",
            "definition": "Definición",
            "section": "Explicación",
            "enunciado": "Enunciado",
            "resolucion": "Resolución",
            "respuesta": "Respuesta",
            "open_supplement": "Suplemento abierto:",
            "not_guide": "No es la bibliografía de la guía.",
        }
    return {
        "preface": "Preface",
        "how": "How to use this book",
        "audit": "Source audit",
        "study": "Study plan",
        "notation": "Notation",
        "formulas": "Formula sheet",
        "solutions": "Solutions",
        "blueprint": "Blueprint",
        "footer": "DRAFT",
        "gap": GAP_LABEL,
        "empty": _EMPTY_PIECE,
        "blocked": "Blocked: no second independent open excerpt and no replayed check.",
        "purpose": "Tip",
        "explanation": "Definition",
        "worked": "Worked problem",
        "self_check": "Self-check",
        "figure_gap": figure_gap(""),
        "science": "A figure does not prove the science.",
        "caption": "The numeric claim in the caption is unchecked.",
        "leftover": "Leftover draft.",
        "note": "This file is a DRAFT. It is not RELEASED.",
        "how_a": "A section may hold several paragraphs. Each substantive paragraph cites a stored excerpt.",
            "how_b": "A chapter has an italic lead, the explanation as body text, at most one tip, definitions only when a term is introduced, one worked problem, and one self-check.",
            "consejo": "Tip",
            "definition": "Definition",
            "section": "Explanation",
            "enunciado": "Statement",
            "resolucion": "Solution",
            "respuesta": "Answer",
        "open_supplement": "Open supplement:",
        "not_guide": "Not the guide bibliography.",
    }


def _display_title(title: str) -> str:
    """Blueprint title without a repeated ``Tema N:`` prefix."""

    stripped = _TEMA_PREFIX.sub("", title).strip()
    return stripped or title.strip()


def _preamble(footer: str) -> list[str]:
    mark = latex_escape(footer)
    return [
        r"\documentclass{book}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage{lmodern}",
        r"\usepackage{graphicx}",
        r"\usepackage[breakable]{tcolorbox}",
        r"\usepackage{fancyhdr}",
        r"\pagestyle{fancy}",
        r"\fancyhf{}",
        r"\fancyfoot[C]{\small " + mark + "}",
        r"\renewcommand{\headrulewidth}{0pt}",
        r"\renewcommand{\footrulewidth}{0pt}",
        r"\fancypagestyle{plain}{%",
        r"  \fancyhf{}",
        r"  \fancyfoot[C]{\small " + mark + "}",
        r"  \renewcommand{\headrulewidth}{0pt}",
        r"  \renewcommand{\footrulewidth}{0pt}",
        r"}",
    ]


def _document(root: Path) -> str:
    kind = book_kind(root)
    language = _language(root)
    copy = _copy(language)
    sections = current_sections(root)
    claims = supported_drafts(root)
    paragraphs = supported_paragraphs(root)
    titles = _source_titles(root)
    sources = _source_records(root)
    excerpts = excerpts_by_id(root)
    counts = bibliography_counts(root)
    book = _book_name(root)
    blocked = blocked_ids(root)
    by_section: dict[str, list[dict[str, object]]] = {}
    for paragraph in paragraphs:
        section = paragraph.get("section")
        if isinstance(section, str):
            by_section.setdefault(section, []).append(paragraph)
    lines = [
        *_preamble(copy["footer"]),
        r"\begin{document}",
        r"\frontmatter",
        r"\title{" + latex_escape(book) + "}",
        r"\author{}",
        r"\date{}",
        r"\maketitle",
        r"\chapter{" + latex_escape(copy["preface"]) + "}",
        r"\noindent " + latex_escape(copy["note"]),
        r"\chapter{" + latex_escape(copy["how"]) + "}",
        r"\noindent " + latex_escape(copy["how_a"]),
        "",
        r"\noindent " + latex_escape(copy["how_b"]),
        r"\tableofcontents",
        r"\mainmatter",
        r"\part{" + latex_escape(book) + "}",
    ]
    if not sections:
        lines.extend(
            [
                r"\chapter{" + latex_escape(copy["blueprint"]) + "}",
                r"\noindent " + latex_escape(copy["empty"]),
            ]
        )
    for section in sections:
        lines.extend(["", r"\chapter{" + latex_escape(_display_title(section["title"])) + "}"])
        section_paragraphs = by_section.get(section["id"], [])
        if not section_paragraphs:
            lines.extend(["", r"\noindent " + latex_escape(copy["gap"])])
            if section["id"] in blocked:
                lines.extend(["", r"\noindent " + latex_escape(copy["blocked"])])
        else:
            lines.extend(_chapter_lines(root, section["id"], section_paragraphs, copy))
        lines.extend(_figure_lines(root, section["id"], copy))
    lines.extend(
        [
            r"\appendix",
            r"\chapter{" + latex_escape(copy["notation"]) + "}",
            r"\noindent " + latex_escape(copy["empty"]),
            r"\chapter{" + latex_escape(copy["formulas"]) + "}",
            r"\noindent " + latex_escape(copy["empty"]),
            r"\chapter{" + latex_escape(copy["solutions"]) + "}",
        ]
    )
    lines.extend(_solution_lines(root, copy))
    lines.extend([r"\chapter{" + latex_escape(copy["audit"]) + "}"])
    lines.extend(_audit_lines(root, paragraphs, claims, titles, excerpts, sources, copy, kind, counts))
    lines.extend(
        [
            r"\chapter{" + latex_escape(copy["study"]) + "}",
            r"\noindent " + latex_escape(copy["empty"]),
            r"\backmatter",
            r"\begin{thebibliography}{99}",
        ]
    )
    lines.extend(_bibliography_lines(root, copy))
    lines.extend([r"\end{thebibliography}", r"\end{document}", ""])
    return "\n".join(lines)


def _chapter_lines(
    root: Path,
    section_id: str,
    paragraphs: list[dict[str, object]],
    copy: dict[str, str],
) -> list[str]:
    """Lead and explanation stay in the body. Only four kinds are boxes."""

    purpose = [record for record in paragraphs if record.get("role") == "purpose"]
    consejo = [record for record in paragraphs if record.get("role") == "consejo"]
    definitions = [record for record in paragraphs if record.get("role") == "definition"]
    self_check = [record for record in paragraphs if record.get("role") == "self_check"]
    body = [
        record
        for record in paragraphs
        if record.get("role") not in {"purpose", "consejo", "definition", "self_check"}
    ]
    lines: list[str] = []
    lines.extend(_italic(_prose_text(purpose)))
    if _prose_text(body):
        lines.extend(["", r"\section{" + latex_escape(copy["section"]) + "}"])
        lines.extend(_plain(_prose_text(body)))
    lines.extend(_box(copy["consejo"], _plain(_prose_text(consejo))))
    for record in definitions:
        lines.extend(_box(copy["definition"], _plain(_prose_text([record]))))
    lines.extend(_worked_box(root, section_id, copy))
    lines.extend(_box(copy["self_check"], _plain(_prose_text(self_check))))
    return lines


def _italic(chunks: list[str]) -> list[str]:
    lines: list[str] = []
    for text in chunks:
        lines.extend(["", r"\noindent\textit{" + latex_escape(text) + "}"])
    return lines


def _plain(chunks: list[str]) -> list[str]:
    lines: list[str] = []
    for text in chunks:
        lines.extend(["", latex_escape(text)])
    return lines


def _prose_text(paragraphs: list[dict[str, object]]) -> list[str]:
    found: list[str] = []
    for paragraph in paragraphs:
        text = paragraph.get("text") if isinstance(paragraph.get("text"), str) else ""
        if text.strip():
            found.append(text)
    return found


def _box(title: str, body: list[str]) -> list[str]:
    if not body:
        return []
    return [
        "",
        r"\begin{tcolorbox}[title={" + latex_escape(title) + "}, breakable]",
        *body,
        r"\end{tcolorbox}",
    ]


def _worked_box(root: Path, section_id: str, copy: dict[str, str]) -> list[str]:
    """One worked problem per chapter, with the statement, the working, and the answer."""

    problems = [record for record in fold_by_id(root / PROBLEMS) if record.get("section") == section_id]
    computations = [
        record
        for record in fold_by_id(root / COMPUTATIONS)
        if record.get("section") == section_id and record.get("status") == "replayed" and record.get("correct") is True
    ]
    if not problems and not computations:
        return []
    problem = problems[0] if problems else {}
    computation = computations[0] if computations else {}
    prompt = problem.get("prompt") if isinstance(problem.get("prompt"), str) else ""
    expected = problem.get("expected") if isinstance(problem.get("expected"), str) else ""
    source = problem.get("source_text") if isinstance(problem.get("source_text"), str) else ""
    expression = computation.get("expression") if isinstance(computation.get("expression"), str) else ""
    result = computation.get("server_result") if isinstance(computation.get("server_result"), str) else ""
    statement = prompt.strip() or expression.strip()
    working = expression.strip() if expression.strip() and expression.strip() != statement else source.strip()
    if not working and expression.strip():
        working = expression.strip()
    answer = result.strip() or expected.strip()
    body = [
        *_labeled(copy["enunciado"], statement),
        *_labeled(copy["resolucion"], working),
        *_labeled(copy["respuesta"], answer),
    ]
    return _box(copy["worked"], body)


def _labeled(label: str, text: str) -> list[str]:
    lines = ["", r"\noindent\textbf{" + latex_escape(label) + "}"]
    if text.strip():
        lines.extend(["", latex_escape(text)])
    return lines


def _figure_lines(root: Path, section_id: str, copy: dict[str, str]) -> list[str]:
    lines: list[str] = []
    for record in figures_in_section(root, section_id):
        output = _checked_output(root, record)
        if output is None:
            lines.extend(["", r"\noindent " + latex_escape(copy["figure_gap"])])
            continue
        caption = record.get("caption") if isinstance(record.get("caption"), str) else ""
        lines.extend(
            [
                "",
                r"\begin{figure}",
                r"\centering",
                r"\includegraphics[width=0.8\textwidth]{" + output + "}",
                r"\caption{" + latex_escape(caption) + "}",
                r"\end{figure}",
                "",
                r"\noindent " + latex_escape(copy["science"]),
            ]
        )
        if record.get("caption_corroboration") == "unchecked":
            lines.extend(["", r"\noindent " + latex_escape(copy["caption"])])
    return lines


def _checked_output(root: Path, record: dict[str, object]) -> str | None:
    if record.get("status") != "checked" or record.get("correct") is not True:
        return None
    output = record.get("output")
    if not isinstance(output, str) or not output.startswith("figures/FIG-") or ".." in Path(output).parts:
        return None
    if not output.endswith(("/figure.png", "/figure.pdf")):
        return None
    path = (root / output).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        return None
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size <= 0:
            return None
    except OSError:
        return None
    return "../" + output


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
    for record in fold_by_id(root / PROBLEMS):
        if record.get("section") != section_id:
            continue
        if record.get("kind") == "rust" and record.get("status") == "checked" and record.get("correct") is True:
            return True
    for record in fold_by_id(root / COMPUTATIONS):
        if record.get("section") == section_id and record.get("status") == "replayed" and record.get("correct") is True:
            return True
    return False


def _solution_lines(root: Path, copy: dict[str, str]) -> list[str]:
    lines: list[str] = []
    for record in fold_by_id(root / PROBLEMS):
        checked = record.get("kind") == "rust" and record.get("status") == "checked" and record.get("correct") is True
        witnessed = record.get("status") == "two_witnesses" or record.get("corroboration") == "two_witnesses"
        if not checked and not witnessed:
            continue
        prompt = record.get("prompt") if isinstance(record.get("prompt"), str) else ""
        if prompt.strip():
            lines.extend(["", latex_escape(prompt)])
    for record in fold_by_id(root / COMPUTATIONS):
        if record.get("status") != "replayed" or record.get("correct") is not True:
            continue
        expression = record.get("expression") if isinstance(record.get("expression"), str) else ""
        result = record.get("server_result") if isinstance(record.get("server_result"), str) else ""
        lines.extend(["", latex_escape(f"{expression} = {result}")])
    if not lines:
        lines.extend(["", r"\noindent " + latex_escape(copy["empty"])])
    return lines


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
) -> list[str]:
    """Source status lives here. Chapter ids are not repeated."""

    lines = ["", r"\noindent " + latex_escape(_status_line(kind, counts, copy))]
    for paragraph in paragraphs:
        label = _audit_label(root, paragraph)
        lines.extend(["", r"\noindent " + latex_escape(_visible_label(copy, label)) + "."])
        lines.extend(_source_notes(paragraph, titles, excerpts, sources, copy, include_text=False))
    for claim in claims:
        identifier = claim.get("id") if isinstance(claim.get("id"), str) else "claim"
        label = _audit_label(root, claim)
        lines.extend(["", r"\noindent " + latex_escape(copy["leftover"])])
        lines.extend(["", r"\noindent " + latex_escape(f"{identifier}: {label}")])
        lines.extend(_source_notes(claim, titles, excerpts, sources, copy, include_text=True))
    for record in fold_by_id(root / AUDITS):
        if record.get("status") != "recorded":
            continue
        identifier = record.get("id") if isinstance(record.get("id"), str) else "audit"
        target = record.get("target") if isinstance(record.get("target"), str) else ""
        if target.startswith("PAR-"):
            target = ""
        check_kind = record.get("kind") if isinstance(record.get("kind"), str) else ""
        lines.extend(["", r"\noindent " + latex_escape(f"{identifier}: {target} {check_kind}".strip())])
    return lines


def _visible_label(copy: dict[str, str], label: str) -> str:
    if copy["footer"] != "Borrador":
        return label
    return {
        "two_witnesses": "dos testimonios",
        "replayed check": "comprobación rehecha",
        "single excerpt": "un extracto",
        "unchecked": "sin comprobar",
    }.get(label, label)


def _bibliography_lines(root: Path, copy: dict[str, str]) -> list[str]:
    lines: list[str] = []
    index = 0
    for record in fold_by_id(root / PUBLIC_BIBLIOGRAPHY):
        title = record.get("title") if isinstance(record.get("title"), str) else ""
        url = record.get("url") if isinstance(record.get("url"), str) else ""
        if not title and not url:
            continue
        index += 1
        origin = record.get("origin") if isinstance(record.get("origin"), str) else ""
        note = " student_notes." if origin == "student_notes" else ""
        lines.append(r"\bibitem{src" + str(index) + "} " + latex_escape(f"{title}. {url}.{note}"))
    if not lines:
        lines.append(r"\bibitem{none} " + latex_escape(copy["empty"]))
    return lines


def _status_line(kind: str, counts: dict[str, int], copy: dict[str, str]) -> str:
    pending = counts.get("pending", 0)
    conflicting = counts.get("conflicting", 0)
    not_cited = counts.get("not_cited", 0)
    if copy["footer"] == "Borrador":
        if kind == BOOK_TOPIC:
            guide = "Un libro de tema no usa una guía universitaria, así que no citada no es una regla de apoyo."
        else:
            guide = "Las fuentes que la guía almacenada no cita quedan fuera."
        return (
            f"Estado de las fuentes: PENDING. "
            f"{pending} pendientes. "
            f"Los conflictos almacenados quedan fuera ({conflicting}). "
            f"{guide} "
            f"Recuento de no citadas: {not_cited}."
        )
    if kind == BOOK_TOPIC:
        guide = "A topic book does not use a university guide, so not cited is not a support rule."
    else:
        guide = "Sources not cited by the stored course guide stay excluded."
    return (
        f"Source status: PENDING. "
        f"{pending} pending. "
        f"Stored conflicts stay excluded ({conflicting}). "
        f"{guide} "
        f"Not cited count: {not_cited}."
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
        text = record.get("text") if isinstance(record.get("text"), str) else ""
        if text.strip():
            lines.extend(["", latex_escape(text)])
    cited_sources = record.get("sources") if isinstance(record.get("sources"), list) else []
    excerpt_ids = record.get("excerpts") if isinstance(record.get("excerpts"), list) else []
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
    source_heading = "Fuentes" if copy["footer"] == "Borrador" else "Sources"
    excerpt_heading = "Extractos" if copy["footer"] == "Borrador" else "Excerpts"
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
    # pdflatex reads the contents file from the previous pass. The second pass
    # puts the new headings on the contents page. Tectonic repeats internally.
    passes = 1 if Path(engine).name.startswith("tectonic") else 2
    detail = ""
    for _ in range(passes):
        compiled, detail = _run_latex(engine, tex_path, out_dir)
        if not compiled:
            return False, detail
    return True, ""


def _run_latex(engine: str, tex_path: Path, out_dir: Path) -> tuple[bool, str]:
    name = Path(engine).name
    if name.startswith("tectonic"):
        command = [engine, "--outdir", str(out_dir), str(tex_path)]
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
        return False, str(exc)[:400]
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
