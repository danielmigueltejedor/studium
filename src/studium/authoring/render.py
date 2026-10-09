"""LaTeX output adapter for a draft. This is not a release build.

Writes ``latex/draft.tex``. Compiles ``latex/draft.pdf`` only when tectonic
or pdflatex is on PATH. A missing engine leaves no PDF behind.
"""

import re
import shutil
import subprocess
from pathlib import Path

from studium.authoring.blueprint import current_sections
from studium.authoring.derivations import derivations_for_section
from studium.authoring.excerpts import excerpts_by_id
from studium.authoring.figures import figures_in_section
from studium.authoring.languages import (
    INVALID_LANGUAGE,
    BookLanguage,
    book_language,
    generic_section_titles,
    messages,
)
from studium.authoring.mathematics import MathError, symbolic_latex, unit_latex
from studium.authoring.notation import notation_registry
from studium.authoring.paragraphs import supported_paragraphs
from studium.authoring.problems import problem_result_current
from studium.authoring.support import corroboration_for_excerpts, supported_drafts
from studium.domain.profiles import BOOK_TOPIC
from studium.research.public_sources import bibliography_counts
from studium.storage.init_project import book_kind, load_project_toml, load_state_holding_lock
from studium.storage.locking import ProjectLocked, project_lock
from studium.storage.records import (
    AUDITS,
    COMPUTATIONS,
    DERIVATIONS,
    FIGURES,
    PROBLEMS,
    PUBLIC_BIBLIOGRAPHY,
    fold_by_id,
)

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
            if book_language(root) is None:
                return _error("render.invalid_language", INVALID_LANGUAGE)
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
    unwritten = _first_unwritten_title(root)
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
        message = (
            "no LaTeX engine on PATH (tectonic or pdflatex). "
            "Wrote the .tex draft. No PDF was created."
        )
        return _render_status(body, status="compiler_missing", message=message, unwritten=unwritten)
    compiled, detail = _compile(engine, tex_path, tex_path.parent)
    if compiled and _is_pdf(pdf_path):
        body["pdf"] = _relative(root, pdf_path)
        return _render_status(body, status="rendered", message="compiled a DRAFT PDF", unwritten=unwritten)
    if pdf_path.exists():
        pdf_path.unlink()
    message = "the LaTeX engine failed. Wrote the .tex draft. No PDF was created."
    if detail:
        message = f"{message} {detail}"
    return _render_status(body, status="render.compile_failed", message=message, unwritten=unwritten)


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


def _first_unwritten_title(root: Path) -> str | None:
    covered = {record.get("section") for record in supported_paragraphs(root)}
    for section in current_sections(root):
        if section["id"] not in covered:
            return _display_title(section["title"])
    return None


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
        "derivations": "Derivaciones",
        "symbol": "Símbolo",
        "meaning": "Significado",
        "units": "Unidades",
        "given": "Datos",
        "unknown": "Incógnita",
        "model": "Modelo físico",
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
        "step_word": "Paso",
    },
}
_EXTRA_BOX_DEFAULTS = {
    "exercises": "Exercises",
    "derivations": "Derivations",
    "symbol": "Symbol",
    "meaning": "Meaning",
    "units": "Units",
    "given": "Given",
    "unknown": "Unknown",
    "model": "Physical model",
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
    "not_reproduced": "not reproduced",
    "step_word": "Step",
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
    """Escape prose, keep explicit math, and wrap Unicode formulas in math mode."""

    text = value.replace("\r\n", "\n").replace("\r", "\n")
    explicit = _explicit_spans(text)
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


def emit_prose(value: str, *, italic: bool = False) -> list[str]:
    """Turn stored paragraphs into paragraphs, display math, and listings."""

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
            rendered = render_text_run(paragraph)
            if _pure_inline_formula(paragraph, rendered):
                inner = rendered.strip()[2:-2].strip()
                lines.append("\\[\n" + inner + "\n\\]")
                continue
            if italic:
                lines.append(r"\noindent\textit{" + rendered + "}")
            else:
                lines.append(rendered)

    for kind, payload, extra in _split_blocks(text):
        if kind == "text":
            text_buf.append(payload)
            continue
        flush()
        if kind == "code":
            lines.extend(_listing_lines(payload, extra))
        else:
            lines.append(payload)
    flush()
    return lines


def _pure_inline_formula(original: str, rendered: str) -> bool:
    if re.search(r"\\\(|\\\[|(?<!\\)\$", original):
        return False
    return re.fullmatch(r"\\\(.+\\\)", rendered.strip(), flags=re.DOTALL) is not None


def _explicit_spans(text: str) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    index = 0
    while index < len(text):
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
    if inner.lstrip()[:1].isdigit() and "=" not in inner and "\\" not in inner:
        return False
    if any(character in _MATH for character in inner) or re.search(r"[=^_\\]", inner):
        return True
    if re.search(r"[A-Za-z]{3,}", inner):
        return False
    return re.fullmatch(r"[A-Za-z0-9 +\-*/().,^_]+", inner) is not None and bool(
        re.search(r"[A-Za-z0-9]", inner)
    )


def _math_chars(text: str) -> str:
    parts: list[str] = []
    for index, character in enumerate(text):
        mapped = _MATH.get(character)
        if mapped is None:
            parts.append(character)
            continue
        if mapped.startswith("\\") and mapped[-1:].isalpha():
            following = text[index + 1] if index + 1 < len(text) else ""
            if following.isascii() and following.isalpha():
                mapped += " "
        parts.append(mapped)
    return "".join(parts)


def _formula_tex(span: str) -> str:
    parts: list[str] = []
    for index, character in enumerate(span):
        mapped = _MATH.get(character)
        if mapped is not None:
            if mapped.startswith("\\") and mapped[-1:].isalpha():
                following = span[index + 1] if index + 1 < len(span) else ""
                if following.isascii() and following.isalpha():
                    mapped += " "
            parts.append(mapped)
            continue
        if character == "%":
            parts.append(r"\%")
        elif character == "#":
            parts.append(r"\#")
        elif character == "&":
            parts.append(r"\&")
        elif character == "\\":
            parts.append(r"\backslash ")
        else:
            parts.append(character)
    return "\\(" + "".join(parts) + "\\)"


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
        if kind != "word" or end - start != 1:
            return False
        if adjacent or (formula_side is not None and formula_side[2] == "op"):
            return True
        return text[start] not in _STOP_LETTERS

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
        if character.isascii() and character.isalpha():
            end = index + 1
            while end < len(text) and text[end].isascii() and text[end].isalpha():
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
        if character in _MATH:
            tokens.append((index, index + 1, "math"))
            index += 1
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
    buf: list[str] = []
    index = 0

    def flush() -> None:
        if buf:
            blocks.append(("text", "".join(buf), ""))
            buf.clear()

    while index < len(text):
        if _line_start(text, index):
            fence = _read_fence(text, index)
            if fence is not None:
                flush()
                code, language, index = fence
                blocks.append(("code", code, language))
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
        if name in _MATH_ENVS:
            return "display", _math_chars(raw), end
        return "display", raw, end
    return None


def _inline_code(code: str) -> str:
    return r"\texttt{" + _texttt(code) + "}"


def _texttt(code: str) -> str:
    parts: list[str] = []
    for character in code:
        if character in _LATEX:
            parts.append(_LATEX[character])
        elif character in _ACCENTS:
            parts.append("{" + _ACCENTS[character] + "}")
        elif character in _MATH:
            parts.append(r"\ensuremath{" + _MATH[character] + "}")
        elif ord(character) < 32 and character != "\t":
            continue
        elif ord(character) > 255:
            parts.append(f"{{U+{ord(character):04X}}}")
        else:
            parts.append(character)
    return "".join(parts)


def _listing_lines(code: str, language: str) -> list[str]:
    body, escape = _listing_body(code)
    options = ["style=studium"]
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
    return _ESCAPE_DELIMS[-1]


def _listing_token(character: str) -> str:
    accent = _ACCENTS.get(character)
    if accent is not None:
        return "{" + accent + "}"
    mapped = _MATH.get(character)
    if mapped is not None:
        return r"\ensuremath{" + mapped + "}"
    return f"{{U+{ord(character):04X}}}"


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


def _unwritten_lines(titles: list[str], copy: dict[str, str]) -> list[str]:
    if not titles:
        return ["", r"\noindent " + latex_escape(copy["empty"])]
    lines: list[str] = []
    for title in titles:
        lines.extend(["", r"\noindent " + latex_escape(f"{title}: {copy['unwritten']}")])
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
    lines.extend(
        [
            r"\usepackage[a4paper,margin=2.5cm]{geometry}",
            r"\usepackage{titlesec}",
            r"\titleformat{\chapter}[display]",
            r"  {\normalfont\filright}{\large\scshape\chaptertitlename\ \thechapter}{1ex}{\huge\bfseries}",
            r"\titlespacing*{\chapter}{0pt}{2.5ex plus 1ex minus .2ex}{2.3ex}",
            r"\titleformat{name=\chapter,numberless}[display]",
            r"  {\normalfont\filright}{}{0pt}{\huge\bfseries}",
            r"\usepackage{graphicx}",
            *( [r"\usepackage{tikz}"] if tikz else [] ),
            *_textbook_packages(),
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


def _document(root: Path) -> str:
    kind = book_kind(root)
    language = _require_language(root)
    copy = messages(language)
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
        *_preamble(copy["footer"], language, copy, tikz=_checked_tikz(root)),
        r"\begin{document}",
        r"\frontmatter",
        *_title_page(root, book, copy),
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
    unwritten: list[str] = []
    for section in sections:
        section_paragraphs = by_section.get(section["id"], [])
        title = _display_title(section["title"])
        if not section_paragraphs:
            unwritten.append(title)
            continue
        lines.extend(["", r"\chapter{" + latex_escape(title) + "}"])
        lines.extend(_chapter_lines(root, section["id"], section_paragraphs, copy, language))
    lines.extend(
        [
            r"\appendix",
            r"\chapter{" + latex_escape(copy["notation"]) + "}",
        ]
    )
    lines.extend(_notation_lines(root, copy, language))
    lines.extend([r"\chapter{" + latex_escape(copy["formulas"]) + "}"])
    lines.extend(_formula_sheet_lines(root, copy))
    lines.extend([r"\chapter{" + latex_escape(copy["solutions"]) + "}"])
    lines.extend(_solution_lines(root, copy, language))
    lines.extend([r"\chapter{" + latex_escape(copy["audit"]) + "}"])
    lines.extend(_audit_lines(root, paragraphs, claims, titles, excerpts, sources, copy, kind, counts))
    lines.extend(
        [
            r"\chapter{" + latex_escape(copy["study"]) + "}",
        ]
    )
    lines.extend(_unwritten_lines(unwritten, copy))
    lines.extend(
        [
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
    language: BookLanguage,
) -> list[str]:
    """Lead and explanation stay in the body. Only four kinds are boxes."""

    purpose: list[str] = []
    consejo: list[str] = []
    definitions: list[str] = []
    self_check: list[str] = []
    body: list[str] = []
    for record in paragraphs:
        role = record.get("role")
        raw = record.get("text") if isinstance(record.get("text"), str) else ""
        if not raw.strip():
            continue
        label, rest = _split_box_lead(raw) if language.babel == "spanish" else (None, raw)
        kind = _box_kind(role, label, language)
        if kind == "consejo":
            consejo.append(_box_body(raw, label, rest, kind, language))
        elif kind == "definition":
            definitions.append(_box_body(raw, label, rest, kind, language))
        elif kind == "self_check":
            self_check.append(_box_body(raw, label, rest, kind, language))
        elif role == "purpose":
            purpose.append(raw)
        else:
            body.append(raw)
    lines: list[str] = []
    lines.extend(_italic(purpose))
    lines.extend(_body_lines(root, section_id, body, copy))
    lines.extend(_box(copy["consejo"], _plain(consejo), "consejo"))
    for text in definitions:
        lines.extend(_box(copy["definition"], _plain([text]), "definition"))
    lines.extend(_derivation_box(root, section_id, language))
    lines.extend(_worked_box(root, section_id, copy, language))
    lines.extend(_exercise_box(root, section_id, language))
    lines.extend(_box(copy["self_check"], _plain(self_check), "self_check"))
    return lines


def _body_lines(root: Path, section_id: str, body: list[str], copy: dict[str, str]) -> list[str]:
    """Consecutive explanation paragraphs are one body. A new section uses the paragraph's own title."""

    lines: list[str] = []
    placed = False
    for kind, value in _body_chunks(body):
        if kind == "section":
            lines.extend(["", r"\section{" + latex_escape(value) + "}"])
            continue
        lines.extend(_plain([value]))
        if not placed:
            lines.extend(_figure_lines(root, section_id, copy))
            placed = True
    if not placed:
        lines.extend(_figure_lines(root, section_id, copy))
    return lines


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
    title = first.strip()
    body = rest.strip()
    if not title or not body or len(title) > 80 or title[-1] in ".!?":
        return None, text
    if title.casefold() in _GENERIC_SECTION:
        return None, body
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


def _italic(chunks: list[str]) -> list[str]:
    lines: list[str] = []
    for text in chunks:
        emitted = emit_prose(text, italic=True)
        if emitted:
            lines.extend(["", *emitted])
    return lines


def _plain(chunks: list[str]) -> list[str]:
    lines: list[str] = []
    for text in chunks:
        emitted = emit_prose(text)
        if emitted:
            lines.extend(["", *emitted])
    return lines


def _box(title: str, body: list[str], kind: str) -> list[str]:
    if not body:
        return []
    style = _BOX_STYLE.get(kind, "studiumdef")
    holds_listing = any(r"\begin{lstlisting}" in line or r"\begin{verbatim}" in line for line in body)
    breaking = "" if holds_listing else ", breakable"
    return [
        "",
        r"\begin{tcolorbox}[title={" + latex_escape(title) + "}, " + style + breaking + "]",
        *body,
        r"\end{tcolorbox}",
    ]


def _domain_profile(root: Path) -> str:
    course = load_project_toml(root).get("course")
    if isinstance(course, dict) and isinstance(course.get("domain_profile"), str):
        return str(course["domain_profile"])
    return "GENERAL"


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
        if record.get("kind") == "rust" and profile != "COMPUTER_SCIENCE":
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
        for record in fold_by_id(root / COMPUTATIONS)
        if record.get("section") == section_id and record.get("status") == "replayed" and record.get("correct") is True
    ]
    if not problems and not computations:
        return []
    problem = problems[0] if problems else {}
    solution = problem.get("solution")
    if isinstance(solution, dict) and solution:
        body = _solution_body(problem, solution, copy, language)
        return _box(copy["worked"], body, "worked")
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


def _solution_body(problem: dict[str, object], solution: dict[str, object], copy: dict[str, str], language: BookLanguage) -> list[str]:
    """A structured, multi-step engineering solution: model, substitution, result."""

    body: list[str] = []
    prompt = problem.get("prompt") if isinstance(problem.get("prompt"), str) else ""
    if prompt.strip():
        body.extend(_labeled(copy["enunciado"], prompt))
    given = solution.get("given")
    if isinstance(given, list):
        body.extend(_given_lines(given, language))
    unknown = solution.get("unknown")
    if isinstance(unknown, str) and unknown.strip():
        body.extend(_labeled(_extra_label(language, "unknown"), unknown))
    model = solution.get("model")
    if isinstance(model, list):
        body.extend(_model_lines(model, language))
    assumptions = solution.get("assumptions")
    if isinstance(assumptions, list):
        body.extend(_bullet_items(_extra_label(language, "assumptions"), [str(item) for item in assumptions], language))
    steps = solution.get("steps")
    if isinstance(steps, list) and steps:
        body.extend(_steps_lines(steps, language))
    else:
        development = solution.get("development")
        if isinstance(development, list) and development:
            body.extend(_numbered_steps([str(item) for item in development], [], language))
    substitution = solution.get("substitution")
    if isinstance(substitution, str) and substitution.strip():
        body.extend(["", r"\noindent\textbf{" + latex_escape(_extra_label(language, "substitution")) + "}"])
        body.extend(_display_math(substitution))
    result = solution.get("result")
    if isinstance(result, str) and result.strip():
        body.extend(["", r"\noindent\textbf{" + latex_escape(_extra_label(language, "result")) + "}"])
        body.extend(_display_math(result))
    interpretation = solution.get("interpretation")
    if isinstance(interpretation, str) and interpretation.strip():
        body.extend(_labeled(_extra_label(language, "interpretation"), interpretation))
    step_checks = problem.get("step_checks")
    if isinstance(step_checks, list):
        body.extend(_step_check_lines(step_checks, language))
    limitations = solution.get("limitations")
    if isinstance(limitations, list):
        body.extend(_bullet_items(_extra_label(language, "limitations"), [str(item) for item in limitations], language))
    mistakes = solution.get("mistakes")
    if isinstance(mistakes, list):
        body.extend(_bullet_items(_extra_label(language, "mistakes"), [str(item) for item in mistakes], language))
    return body


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


def _symbol_tex(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        return ""
    try:
        return symbolic_latex(cleaned)
    except MathError:
        return r"\mathrm{" + latex_escape(cleaned) + "}"


def _unit_tex(unit: str) -> str:
    try:
        return unit_latex(unit)
    except MathError:
        return r"\mathrm{" + latex_escape(unit.strip()) + "}"


def _display_math(tex: str) -> list[str]:
    stripped = tex.strip()
    if not stripped:
        return []
    if stripped.startswith(r"\[") and stripped.endswith(r"\]"):
        return ["", stripped]
    if stripped.startswith(r"\(") and stripped.endswith(r"\)"):
        return ["", r"\[" + stripped[2:-2] + r"\]"]
    if stripped.startswith("$") and stripped.endswith("$") and len(stripped) > 2:
        return ["", r"\[" + stripped[1:-1] + r"\]"]
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
            meaning = raw.get("meaning") if isinstance(raw.get("meaning"), str) else ""
            units = raw.get("units") if isinstance(raw.get("units"), str) else ""
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
        item = "$" + symbol + r" = " + latex_escape(value)
        if unit and unit.strip() and unit.strip().lower() not in {"dimensionless", "adimensional", "1"}:
            item += r"\," + _unit_tex(unit)
        item += "$"
        meaning = raw.get("meaning")
        if isinstance(meaning, str) and meaning.strip():
            item += " — " + render_text_run(meaning.strip())
        lines.append(r"\item " + item)
    lines.append(r"\end{itemize}")
    return lines


def _model_lines(model: list[object], language: BookLanguage) -> list[str]:
    if not model:
        return []
    lines = ["", r"\noindent\textbf{" + latex_escape(_extra_label(language, "model")) + "}"]
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
        phrase = _extra_label(language, "reproduced") if check.get("reproduced") is True else _extra_label(language, "not_reproduced")
        item = latex_escape(_extra_label(language, "step_word")) + " " + latex_escape(number)
        if value:
            item += r": $" + render_text_run(value) + "$"
        item += " — " + latex_escape(phrase)
        lines.append(r"\item " + item)
    lines.append(r"\end{itemize}")
    return lines


def _derivation_box(root: Path, section_id: str, language: BookLanguage) -> list[str]:
    """The recorded derivations of this chapter with their stored check status."""

    records = derivations_for_section(root, section_id)
    if not records:
        return []
    label = _extra_label(language, "derivations")
    body: list[str] = []
    for record in records:
        name = record.get("name") if isinstance(record.get("name"), str) else ""
        equation = record.get("equation") if isinstance(record.get("equation"), str) else ""
        body.extend(["", r"\noindent\textbf{" + latex_escape(name.strip() or label) + "}"])
        if equation.strip():
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
        body.extend(["", r"\noindent\footnotesize " + latex_escape(_status_phrase(status, language)) + "."])
    return _box(label, body, "derivation")


def _exercise_box(root: Path, section_id: str, language: BookLanguage) -> list[str]:
    """The practice set of this chapter. Solutions live in the appendix."""

    records = _practice_records(root, section_id)
    if not records:
        return []
    label = _extra_label(language, "exercises")
    body: list[str] = []
    for index, record in enumerate(records, 1):
        prompt = record.get("prompt") if isinstance(record.get("prompt"), str) else ""
        difficulty = record.get("difficulty") if isinstance(record.get("difficulty"), str) else ""
        problem_type = record.get("problem_type") if isinstance(record.get("problem_type"), str) else ""
        tags = [tag for tag in (difficulty.strip(), problem_type.strip()) if tag]
        head = str(index)
        if tags:
            head += " (" + ", ".join(tags) + ")"
        body.extend(["", r"\noindent\textbf{" + latex_escape(head) + "}"])
        if prompt.strip():
            body.extend(emit_prose(prompt.strip()))
    return _box(label, body, "exercise")


def _figure_lines(root: Path, section_id: str, _copy: dict[str, str]) -> list[str]:
    """Checked drawings inline. No float, so a short drawing does not take a page."""

    lines: list[str] = []
    for record in figures_in_section(root, section_id):
        output = _checked_output(root, record)
        if output is None:
            continue
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
            fitted = _fit_block(r"\includegraphics{" + output + "}", consume_box=True)
        caption = record.get("caption") if isinstance(record.get("caption"), str) else ""
        lines.extend(
            [
                "",
                r"\par\vspace{\baselineskip}",
                r"\noindent\begin{minipage}{\linewidth}",
                r"\centering",
            ]
        )
        lines.extend(fitted)
        if caption.strip():
            lines.extend([r"\par\nopagebreak", r"{\small " + render_text_run(caption) + r"\par}"])
        lines.extend(
            [
                r"\end{minipage}",
                r"\par\vspace{\baselineskip}",
            ]
        )
    return lines


def _checked_tikz(root: Path) -> bool:
    for record in fold_by_id(root / FIGURES):
        if record.get("kind") == "tikz" and _checked_output(root, record) is not None:
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
        r"\resizebox{\wd0}{!}{" + shipped + r"}%",
        r"\fi",
        r"\fi",
        r"\endgroup",
    ]


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
    for record in _worked_problem_records(root, section_id):
        if (
            record.get("kind") == "rust"
            and record.get("status") == "checked"
            and record.get("correct") is True
            and problem_result_current(root, record)
        ):
            return True
    for record in fold_by_id(root / COMPUTATIONS):
        if record.get("section") == section_id and record.get("status") == "replayed" and record.get("correct") is True:
            return True
    return False


def _notation_lines(root: Path, copy: dict[str, str], language: BookLanguage) -> list[str]:
    """The notation appendix from the registry: one row per symbol."""

    registry = notation_registry(root)
    if not registry:
        return ["", r"\noindent " + latex_escape(copy["empty"])]
    symbol_head = latex_escape(_extra_label(language, "symbol"))
    meaning_head = latex_escape(_extra_label(language, "meaning"))
    units_head = latex_escape(_extra_label(language, "units"))
    lines = [
        "",
        r"\begin{center}",
        r"\begin{tabular}{@{}cp{7cm}l@{}}",
        rf"\textbf{{{symbol_head}}} & \textbf{{{meaning_head}}} & \textbf{{{units_head}}} \\",
        r"\hline",
    ]
    for symbol, entry in sorted(registry.items()):
        meaning = latex_escape(str(entry.get("meaning") or ""))
        units = latex_escape(str(entry.get("units") or ""))
        lines.append(rf"{render_text_run(symbol)} & {meaning} & {units} \\")
    lines.extend([r"\end{tabular}", r"\end{center}"])
    return lines


def _formula_sheet_lines(root: Path, copy: dict[str, str]) -> list[str]:
    """The formula sheet from the recorded derivations: name and final equation."""

    records = [
        record
        for record in fold_by_id(root / DERIVATIONS)
        if isinstance(record.get("equation"), str) and record["equation"].strip()
    ]
    if not records:
        return ["", r"\noindent " + latex_escape(copy["empty"])]
    lines: list[str] = []
    for record in records:
        name = str(record.get("name") or "").strip()
        equation = str(record["equation"]).strip()
        if name:
            lines.extend(["", r"\noindent\textbf{" + latex_escape(name) + "}"])
        lines.extend(["", *emit_prose(equation)])
    return lines


def _solution_lines(root: Path, copy: dict[str, str], language: BookLanguage) -> list[str]:
    """Checked solutions only. Exercises without a checked solution are named, not invented."""

    lines: list[str] = []
    profile = _domain_profile(root)
    numbering = _practice_numbering(root)
    seen_practice: set[str] = set()
    solved_practice: set[str] = set()
    exercise_label = _extra_label(language, "exercises")
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
        if not checked and not witnessed:
            continue
        prompt = record.get("prompt") if isinstance(record.get("prompt"), str) else ""
        if not prompt.strip():
            continue
        if is_practice and isinstance(identifier, str):
            solved_practice.add(identifier)
            number = numbering.get(identifier, 0)
            lines.extend(["", r"\noindent\textbf{" + latex_escape(f"{exercise_label} {number}") + "}"])
        lines.extend(["", *emit_prose(prompt)])
        expected = record.get("expected") if isinstance(record.get("expected"), str) else ""
        if expected.strip() and witnessed:
            lines.extend(
                ["", r"\noindent\textbf{" + latex_escape(copy["respuesta"]) + "} " + latex_escape(expected.strip())]
            )
    for record in fold_by_id(root / COMPUTATIONS):
        if record.get("status") != "replayed" or record.get("correct") is not True:
            continue
        expression = record.get("expression") if isinstance(record.get("expression"), str) else ""
        result = record.get("server_result") if isinstance(record.get("server_result"), str) else ""
        lines.extend(["", _formula_line(f"{expression} = {result}")])
    unsolved = len(seen_practice - solved_practice)
    if unsolved:
        if language.babel == "spanish":
            note = f"{unsolved} ejercicios todavía sin solución comprobada."
        else:
            note = f"{unsolved} exercises still without a checked solution."
        lines.extend(["", r"\noindent\textit{" + latex_escape(note) + "}"])
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
    for record in fold_by_id(root / FIGURES):
        identifier = record.get("id") if isinstance(record.get("id"), str) else "figure"
        if _checked_output(root, record) is None:
            lines.extend(["", r"\noindent " + latex_escape(f"{identifier}: {copy['figure_gap']}")])
            continue
        if record.get("caption_corroboration") == "unchecked":
            lines.extend(["", r"\noindent " + latex_escape(f"{identifier}: {copy['caption']}")])
    return lines


def _visible_label(copy: dict[str, str], label: str) -> str:
    return {
        "two_witnesses": copy["two_witnesses"],
        "replayed check": copy["replayed"],
        "single excerpt": copy["single_excerpt"],
        "unchecked": copy["unchecked"],
    }.get(label, label)


def _url_tex(url: str) -> str:
    """A clickable, breakable URL. ``\\url`` keeps the raw characters and lets
    TeX break at ``/``, ``.`` and ``-`` so a long address cannot overflow."""

    cleaned = url.strip().replace("\\", "").replace("{", "").replace("}", "").replace("\n", "").replace(" ", "")
    if not cleaned:
        return ""
    if "://" in cleaned or cleaned.startswith("www."):
        return r"\url{" + cleaned + "}"
    return latex_escape(cleaned)


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
        parts = [latex_escape(f"{title}.")] if title.strip() else []
        rendered_url = _url_tex(url)
        if rendered_url:
            parts.append(rendered_url)
        if note:
            parts.append(latex_escape(note.strip()))
        lines.append(r"\bibitem{src" + str(index) + "} " + " ".join(parts))
    if not lines:
        lines.append(r"\bibitem{none} " + latex_escape(copy["empty"]))
    return lines


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
        text = record.get("text") if isinstance(record.get("text"), str) else ""
        if text.strip():
            lines.extend(["", *emit_prose(text)])
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
