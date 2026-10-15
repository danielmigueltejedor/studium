"""Text of a user-provided file, read only to check that a quoted excerpt is in it.

The extracted text is never stored in the project. A quote found in the file
proves where the words come from, not that they are correct.
"""

import html
import re
import shutil
import subprocess
import tempfile
import unicodedata
import zipfile
from io import BytesIO
from pathlib import Path

_PDFTOTEXT_TIMEOUT = 120
_PDFTOPPM_TIMEOUT = 120
MIN_DPI = 50
MAX_DPI = 200
DEFAULT_DPI = 110
_TEXT_TYPES = frozenset({"text/plain", "text/markdown", "text/x-tex", "text/csv", "text/html"})
_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
_EPUB = "application/epub+zip"
_PDF = "application/pdf"
_DASHES: dict[int, str] = dict.fromkeys((0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2212), "-")
_QUOTES: dict[int, str] = {0x2018: "'", 0x2019: "'", 0x201C: '"', 0x201D: '"', 0x00AB: '"', 0x00BB: '"'}


def extract_pages(data: bytes, media_type: str) -> tuple[list[str] | None, str, str | None]:
    """Pages (PDF), slides (PPTX), or one page of text. ``None`` with a reason when unreadable."""

    if media_type == _PDF:
        return _pdf_pages(data)
    if media_type in _TEXT_TYPES:
        try:
            text = data.decode("utf-8")
        except UnicodeError:
            return None, "utf-8", "the file is not UTF-8 text"
        if media_type == "text/html":
            text = _strip_markup(text)
        return [text], "utf-8", None
    if media_type == _DOCX:
        return _zip_xml(data, lambda name: name == "word/document.xml", "docx")
    if media_type == _PPTX:
        return _zip_xml(data, lambda name: re.fullmatch(r"ppt/slides/slide\d+\.xml", name) is not None, "pptx")
    if media_type == _EPUB:
        return _zip_xml(data, lambda name: name.endswith((".xhtml", ".html", ".htm")), "epub", one_page=True)
    return None, "none", f"text cannot be read from {media_type}"


def normalize(text: str) -> str:
    """Comparison form: NFKC (ligatures), joined line-break hyphens, plain dashes and quotes, one space."""

    folded = unicodedata.normalize("NFKC", text).translate(_DASHES).translate(_QUOTES)
    folded = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", folded)
    return re.sub(r"\s+", " ", folded).strip()


def find_quote(pages: list[str], quote: str, page: int | None) -> tuple[bool, list[int]]:
    """Whether the quote is in the given page (1-based) or anywhere; the pages that hold it."""

    needle = normalize(quote)
    found = [index + 1 for index, text in enumerate(pages) if needle and needle in normalize(text)]
    # A quote may cross a page break.
    if not found and needle and page is None and len(pages) > 1 and needle in normalize("\n".join(pages)):
        return True, []
    if page is not None:
        return page in found, found
    return bool(found), found


def _pdf_pages(data: bytes) -> tuple[list[str] | None, str, str | None]:
    tool = shutil.which("pdftotext")
    if tool is None:
        return None, "pdftotext", "pdftotext (poppler) is not installed, so the PDF text cannot be checked"
    with tempfile.TemporaryDirectory(prefix="studium-local-") as folder:
        path = Path(folder) / "source.pdf"
        path.write_bytes(data)
        try:
            run = subprocess.run(
                [tool, "-enc", "UTF-8", str(path), "-"],
                capture_output=True,
                timeout=_PDFTOTEXT_TIMEOUT,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None, "pdftotext", "pdftotext could not read the PDF"
    if run.returncode != 0:
        return None, "pdftotext", "pdftotext could not read the PDF"
    text = run.stdout.decode("utf-8", errors="replace")
    pages = text.split("\f")
    if pages and not pages[-1].strip():
        pages = pages[:-1]
    if not any(page.strip() for page in pages):
        return None, "pdftotext", "the PDF has no text layer (a scan needs OCR first)"
    return pages, "pdftotext", None


def _zip_xml(data: bytes, wanted, label: str, one_page: bool = False) -> tuple[list[str] | None, str, str | None]:
    try:
        archive = zipfile.ZipFile(BytesIO(data))
    except zipfile.BadZipFile:
        return None, label, f"the {label} file is not a readable archive"
    names = sorted((name for name in archive.namelist() if wanted(name)), key=_natural)
    if not names:
        return None, label, f"the {label} file has no text parts"
    pages: list[str] = []
    for name in names:
        try:
            raw = archive.read(name).decode("utf-8", errors="replace")
        except (KeyError, OSError, zipfile.BadZipFile):
            return None, label, f"the {label} file could not be read"
        pages.append(_strip_markup(raw))
    if one_page:
        pages = ["\n".join(pages)]
    return pages, label, None


def _strip_markup(raw: str) -> str:
    text = re.sub(r"<(?:w:p|a:p|p|br|div|h\d|li|tr)\b[^>]*/?>", "\n", raw)
    text = re.sub(r"<w:tab\b[^>]*/>", " ", text)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text)


def _natural(name: str) -> list[object]:
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", name)]


def pdf_page_count(data: bytes) -> int | None:
    """Number of pages of a PDF (poppler ``pdfinfo``), or ``None`` when it cannot be read."""

    tool = shutil.which("pdfinfo")
    if tool is None:
        return None
    with tempfile.TemporaryDirectory(prefix="studium-local-") as folder:
        path = Path(folder) / "source.pdf"
        path.write_bytes(data)
        try:
            run = subprocess.run([tool, str(path)], capture_output=True, timeout=_PDFTOTEXT_TIMEOUT, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return None
    if run.returncode != 0:
        return None
    found = re.search(r"^Pages:\s+(\d+)", run.stdout.decode("utf-8", errors="replace"), re.MULTILINE)
    return int(found.group(1)) if found else None


def render_pdf_page(data: bytes, page: int, dpi: int = DEFAULT_DPI) -> tuple[bytes | None, str | None]:
    """One PDF page as PNG bytes (poppler ``pdftoppm``), or ``None`` with the reason."""

    tool = shutil.which("pdftoppm")
    if tool is None:
        return None, "pdftoppm (poppler) is not installed, so a page cannot be rendered"
    with tempfile.TemporaryDirectory(prefix="studium-page-") as folder:
        source = Path(folder) / "source.pdf"
        source.write_bytes(data)
        target = Path(folder) / "page"
        try:
            run = subprocess.run(
                [tool, "-f", str(page), "-l", str(page), "-r", str(dpi), "-png", "-singlefile", str(source), str(target)],
                capture_output=True,
                timeout=_PDFTOPPM_TIMEOUT,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None, "pdftoppm could not render the page"
        image = Path(f"{target}.png")
        if run.returncode != 0 or not image.is_file():
            return None, "pdftoppm could not render the page"
        return image.read_bytes(), None


def png_size(image: bytes) -> tuple[int, int] | None:
    """Width and height from a PNG header."""

    if len(image) < 24 or not image.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    return int.from_bytes(image[16:20], "big"), int.from_bytes(image[20:24], "big")
