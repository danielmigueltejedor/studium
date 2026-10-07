"""LaTeX output adapter for a draft. This is not a release build.

Writes ``latex/draft.tex``. Compiles ``latex/draft.pdf`` only when tectonic
or pdflatex is on PATH. A missing engine leaves no PDF behind.
"""

import shutil
import subprocess
from pathlib import Path

from studium.authoring.blueprint import current_sections
from studium.authoring.excerpts import excerpts_by_id
from studium.authoring.paragraphs import GAP_LABEL, supported_paragraphs
from studium.authoring.support import supported_drafts
from studium.domain.profiles import BOOK_TOPIC
from studium.research.public_sources import bibliography_counts
from studium.storage.init_project import book_kind, load_project_toml, load_state_holding_lock
from studium.storage.locking import ProjectLocked, project_lock
from studium.storage.records import PUBLIC_BIBLIOGRAPHY, fold_by_id

_TEX_NAME = "draft.tex"
_PDF_NAME = "draft.pdf"
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
    escaped: list[str] = []
    for character in value:
        replacement = _LATEX.get(character)
        if replacement is not None:
            escaped.append(replacement)
        elif ord(character) < 32 and character not in "\n\t":
            continue
        else:
            escaped.append(character)
    return "".join(escaped)


def _document(root: Path) -> str:
    kind = book_kind(root)
    sections = current_sections(root)
    claims = supported_drafts(root)
    paragraphs = supported_paragraphs(root)
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
        r"\documentclass{article}",
        r"\makeatletter",
        r"\ifx\XeTeXrevision\undefined",
        r"  \ifx\directlua\undefined",
        r"    \usepackage[utf8]{inputenc}",
        r"    \usepackage[T1]{fontenc}",
        r"  \fi",
        r"\fi",
        r"\makeatother",
        r"\begin{document}",
        r"\begin{center}",
        r"{\Large\bfseries DRAFT}",
        r"\end{center}",
        "",
        r"\noindent " + latex_escape(_status_line(kind, counts)),
        "",
        r"\noindent Book: " + latex_escape(book),
        "",
        r"\section*{Outline}",
    ]
    if not sections:
        lines.append("No blueprint is stored.")
    for section in sections:
        lines.extend(["", r"\section{" + latex_escape(section["title"]) + "}"])
        section_paragraphs = by_section.get(section["id"], [])
        if not section_paragraphs:
            lines.extend(["", r"\noindent " + latex_escape(GAP_LABEL)])
            continue
        for paragraph in section_paragraphs:
            lines.extend(_claim_lines(paragraph, titles, excerpts, sources))
    lines.extend(["", r"\section*{Draft claims}"])
    if not claims:
        lines.append("No supported draft claims.")
    for claim in claims:
        lines.extend(_claim_lines(claim, titles, excerpts, sources))
    lines.extend(["", r"\end{document}", ""])
    return "\n".join(lines)


def _status_line(kind: str, counts: dict[str, int]) -> str:
    pending = counts.get("pending", 0)
    conflicting = counts.get("conflicting", 0)
    not_cited = counts.get("not_cited", 0)
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


def _claim_lines(
    claim: dict[str, object],
    titles: dict[str, str],
    excerpts: dict[str, dict[str, object]],
    sources: dict[str, dict[str, object]] | None = None,
) -> list[str]:
    text = claim.get("text") if isinstance(claim.get("text"), str) else ""
    cited_sources = claim.get("sources") if isinstance(claim.get("sources"), list) else []
    excerpt_ids = claim.get("excerpts") if isinstance(claim.get("excerpts"), list) else []
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
                f"Open supplement: {excerpt_id} {title} (PENDING). Not the guide bibliography."
            )
        else:
            excerpt_labels.append(f"{excerpt_id} {title} (PENDING)")
    identifier = claim.get("id") if isinstance(claim.get("id"), str) else "draft"
    lines = [
        "",
        r"\noindent\textbf{" + latex_escape(identifier) + "}",
        "",
        latex_escape(text),
    ]
    if labels:
        lines.extend(["", r"\noindent Sources: " + latex_escape(", ".join(labels)) + "."])
    if excerpt_labels:
        lines.extend(["", r"\noindent Excerpts: " + latex_escape(", ".join(excerpt_labels)) + "."])
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


def _compile(engine: str, tex_path: Path, out_dir: Path) -> tuple[bool, str]:
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
