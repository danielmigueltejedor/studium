"""Pictures taken from an open source, with their credit and licence.

A history chapter wants a map, a manuscript page or a portrait; a biology
chapter wants a micrograph. Those are not drawn from data, so they cannot be a
TikZ or Python figure. An image figure keeps what a reader and a licence need:

* the page the picture was opened from, its title and its author;
* a licence from a short allowlist of open licences (public domain, CC0,
  CC BY, CC BY-SA). Anything else is refused, and so is a missing author;
* the file itself, which the client downloaded into the book, as a PNG or JPEG
  of a bounded size. The server never fetches the URL. It stores the file hash,
  and the picture renders only while the file still has that hash.

That is provenance and licence bookkeeping, not a legal opinion: the licence
text on the source page is what the client read, and it can be wrong.
"""

import hashlib
import json
import re
import shutil
import struct
from pathlib import Path
from urllib.parse import urlsplit

MAX_BYTES = 3_000_000
MIN_SIDE = 200
MAX_SIDE = 6_000
_META_LIMIT = 400

_LICENSES: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (re.compile(r"^(?:cc0|cc[- ]?zero)(?:\s*1\.0)?$", re.I), "CC0 1.0", "https://creativecommons.org/publicdomain/zero/1.0/"),
    (
        re.compile(r"^(?:public[- ]domain|pd|dominio p[uú]blico|pd[- ]?(?:old|art|us|usgov)[\w-]*)$", re.I),
        "Public domain",
        "https://creativecommons.org/publicdomain/mark/1.0/",
    ),
    (re.compile(r"^cc[- ]?by[- ]?sa[- ]?(\d\.\d)$", re.I), "CC BY-SA {}", "https://creativecommons.org/licenses/by-sa/{}/"),
    (re.compile(r"^cc[- ]?by[- ]?(\d\.\d)$", re.I), "CC BY {}", "https://creativecommons.org/licenses/by/{}/"),
)
_VERSIONS = frozenset({"1.0", "2.0", "2.5", "3.0", "4.0"})
ALLOWED_LICENSES_TEXT = "public domain, CC0, CC BY 1.0-4.0 or CC BY-SA 1.0-4.0"


def normalise_license(value: object) -> tuple[str, str] | None:
    """The canonical licence name and its deed URL, or ``None`` when not allowed."""

    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    for pattern, name, deed in _LICENSES:
        match = pattern.match(text)
        if match is None:
            continue
        if match.groups():
            version = match.group(1)
            if version not in _VERSIONS:
                return None
            return name.format(version), deed.format(version)
        return name, deed
    return None


def validate_image(root: Path, image: object) -> tuple[dict[str, object] | None, str | None, str | None]:
    """The stored fields of an image figure, or ``(None, code, message)``.

    ``image.path`` names the downloaded file inside the book. It is read here
    and its hash is stored; the original path is kept for the check.
    """

    if not isinstance(image, dict):
        return None, "mcp.invalid_input", "an image figure needs an image object"
    meta: dict[str, object] = {}
    for key in ("title", "author"):
        value = image.get(key)
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > _META_LIMIT:
            return None, "mcp.invalid_input", f"image.{key} is required"
        meta[key] = " ".join(value.split())
    url = image.get("url")
    if not _http(url):
        return None, "mcp.invalid_input", "image.url must be the http or https page the picture was opened from"
    meta["url"] = str(url).strip()
    licence = normalise_license(image.get("license"))
    if licence is None:
        return (
            None,
            "figure.license_not_allowed",
            f"image.license must be one of: {ALLOWED_LICENSES_TEXT}. Other licences are not used.",
        )
    meta["license"], deed = licence
    meta["license_url"] = deed
    if image.get("license_url") is not None:
        if not _http(image.get("license_url")):
            return None, "mcp.invalid_input", "image.license_url must be an http or https address"
        meta["license_url"] = str(image["license_url"]).strip()
    for key in ("credit", "date"):
        value = image.get(key)
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > _META_LIMIT:
            return None, "mcp.invalid_input", f"image.{key} must be short text"
        meta[key] = " ".join(value.split())
    located, code, message = locate(root, image.get("path"))
    if located is None:
        return None, code, message
    data = located.read_bytes()
    kind = image_format(data)
    if kind is None:
        return None, "figure.image_invalid", "the file is not a PNG or JPEG image"
    size = dimensions(data, kind)
    if size is None or min(size) < MIN_SIDE or max(size) > MAX_SIDE:
        return (
            None,
            "figure.image_invalid",
            f"the picture must be between {MIN_SIDE} and {MAX_SIDE} pixels on each side",
        )
    meta["path"] = located.relative_to(root.resolve()).as_posix()
    meta["format"] = kind
    meta["sha256"] = hashlib.sha256(data).hexdigest()
    meta["bytes"] = len(data)
    meta["width"], meta["height"] = size
    return meta, None, None


def locate(root: Path, value: object) -> tuple[Path | None, str | None, str | None]:
    """A regular, non-link file inside the book, within the size bound."""

    if not isinstance(value, str) or not value.strip() or len(value) > 300:
        return None, "mcp.invalid_input", "image.path is required: the downloaded file, relative to the book"
    candidate = root / value.strip()
    try:
        resolved = candidate.resolve()
        resolved.relative_to(root.resolve())
    except (OSError, ValueError):
        return None, "figure.path_escaped", "the image must be inside the book"
    if candidate.is_symlink() or not resolved.is_file():
        return None, "figure.image_missing", "no regular image file at image.path"
    size = resolved.stat().st_size
    if size <= 0 or size > MAX_BYTES:
        return None, "figure.image_invalid", f"the image must be non-empty and at most {MAX_BYTES // 1_000_000} MB"
    return resolved, None, None


def image_format(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    return None


def dimensions(data: bytes, kind: str) -> tuple[int, int] | None:
    """Width and height from the file header, without an imaging library."""

    try:
        if kind == "png":
            width, height = struct.unpack(">II", data[16:24])
            return int(width), int(height)
        index = 2
        while index + 9 < len(data):
            if data[index] != 0xFF:
                index += 1
                continue
            marker = data[index + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                index += 2
                continue
            length = struct.unpack(">H", data[index + 2 : index + 4])[0]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                height, width = struct.unpack(">HH", data[index + 5 : index + 9])
                return int(width), int(height)
            index += 2 + length
    except (struct.error, IndexError):
        return None
    return None


def install(root: Path, record: dict[str, object], work: Path) -> tuple[str | None, str | None]:
    """Copy the verified file to ``figures/<id>/figure.<ext>``; return its book-relative path."""

    meta = record.get("image")
    if not isinstance(meta, dict):
        return None, "the figure has no image record"
    located, _code, message = locate(root, meta.get("path"))
    if located is None:
        return None, message
    data = located.read_bytes()
    if hashlib.sha256(data).hexdigest() != meta.get("sha256"):
        return None, "the file changed since it was recorded; record the figure again"
    kind = image_format(data)
    if kind is None or kind != meta.get("format"):
        return None, "the file is not the recorded PNG or JPEG"
    work.mkdir(parents=True, exist_ok=True)
    destination = work / f"figure.{kind}"
    if destination.resolve() != located:
        shutil.copyfile(located, destination)
    return destination.resolve().relative_to(root.resolve()).as_posix(), None


def credit_line(record: dict[str, object]) -> str:
    """Author, title, licence and page: the credit a reuse licence asks to keep."""

    meta = record.get("image")
    if not isinstance(meta, dict):
        return ""
    parts = [str(meta.get("author") or ""), f"«{meta.get('title')}»" if meta.get("title") else "", str(meta.get("license") or "")]
    return ", ".join(part for part in parts if part)


def credit_url(record: dict[str, object]) -> str:
    meta = record.get("image")
    return str(meta.get("url") or "") if isinstance(meta, dict) else ""


def source_text(meta: dict[str, object]) -> str:
    """The canonical text stored as the figure's ``source`` and hashed with it."""

    return json.dumps(meta, sort_keys=True, ensure_ascii=False)


def _http(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 1000:
        return False
    parts = urlsplit(value.strip())
    return parts.scheme in ("http", "https") and bool(parts.netloc)
