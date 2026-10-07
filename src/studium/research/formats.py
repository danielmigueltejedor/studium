"""Accepted local formats. Unknown bytes are not executed."""

from pathlib import Path

ACCEPTED_FORMATS: tuple[str, ...] = (
    "pdf",
    "docx",
    "pptx",
    "xlsx",
    "xls",
    "csv",
    "txt",
    "md",
    "tex",
    "html",
    "epub",
)

_MEDIA: dict[str, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "csv": "text/csv",
    "txt": "text/plain",
    "md": "text/markdown",
    "tex": "text/x-tex",
    "html": "text/html",
    "epub": "application/epub+zip",
}

_ZIP = frozenset({"docx", "pptx", "xlsx", "epub"})
_TEXT = frozenset({"csv", "txt", "md", "tex", "html"})


def sniff(filename: str, data: bytes) -> tuple[str, str] | None:
    extension = Path(filename).suffix.lower().lstrip(".")
    if extension not in _MEDIA:
        return None
    if extension == "pdf" and not data.startswith(b"%PDF"):
        return None
    if extension in _ZIP and not data.startswith(b"PK\x03\x04"):
        return None
    if extension == "xls" and not data.startswith(b"\xd0\xcf\x11\xe0"):
        return None
    if extension in _TEXT:
        try:
            data.decode("utf-8")
        except UnicodeError:
            return None
    return extension, _MEDIA[extension]
