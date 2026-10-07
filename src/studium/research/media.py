"""A video the client already opened.

The server stores a YouTube URL and transcript text. The text is untrusted
data, not truth. The video file is not downloaded. A public caption fetch is
limited to one video id and does not log in. Missing captions are reported
and not invented.
"""

import hashlib
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from html import unescape
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from studium.policy.trust import contains_directive, directive_changes_policy
from studium.research.public_sources import license_forbids_use, openstax_host, unauthorized_copy
from studium.storage.init_project import load_state_holding_lock
from studium.storage.locking import ProjectLocked, project_lock
from studium.storage.migrate import utc_now
from studium.storage.records import MEDIA, append_jsonl, fold_by_id

_AUDIT = "audit/audit.jsonl"
_MAX_TEXT = 200_000
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YOUTUBE_HOSTS = frozenset({"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"})
_TIMEDTEXT = "https://www.youtube.com/api/timedtext"
_LICENSE = "a source whose license forbids this use is not recorded, as with OpenStax"


def record_media(
    root: Path,
    *,
    url: object,
    transcript: object = None,
    title: object = None,
    license_forbids: object = None,
    unauthorized: object = None,
    actor: dict[str, object] | None = None,
) -> dict[str, object]:
    """Store one opened video. A supplied transcript is not fetched again."""

    if unauthorized_copy(unauthorized) or unauthorized_copy(license_forbids):
        return _error("source.unauthorized", "pirate or unauthorized copies are not recorded")
    if license_forbids_use(license_forbids):
        return _error("source.license_forbidden", _LICENSE)
    opened = _http_url(url)
    if opened is None:
        return _error("mcp.invalid_input", "url must be an http or https URL the client already opened")
    if openstax_host(opened) or _video_file(opened):
        return _error("source.license_forbidden", _LICENSE if openstax_host(opened) else "the video file is not downloaded")
    video_id = youtube_id(opened)
    if video_id is None:
        return _error("mcp.invalid_input", "url must be one YouTube video the client opened")
    cleaned_title = _title(title) or f"YouTube {video_id}"
    supplied, text_error = _transcript(transcript)
    if text_error is not None:
        return _error("mcp.invalid_input", text_error)
    if supplied is not None:
        if directive_changes_policy(supplied):
            return _error("policy.overridden", "transcript text changed policy")
        return _store(
            root,
            url=opened,
            video_id=video_id,
            title=cleaned_title,
            transcript=supplied,
            transcript_origin="client",
            actor=actor,
        )
    fetched = fetch_public_captions(video_id)
    if not fetched:
        return {
            "status": "captions_missing",
            "message": "no public captions for this video. No transcript was invented.",
            "video_id": video_id,
            "downloaded": False,
        }
    if directive_changes_policy(fetched):
        return _error("policy.overridden", "transcript text changed policy")
    return _store(
        root,
        url=opened,
        video_id=video_id,
        title=cleaned_title,
        transcript=fetched,
        transcript_origin="public_captions",
        actor=actor,
    )


def fetch_public_captions(video_id: str) -> str | None:
    """Read public timed-text captions for one video id. No login and no video file."""

    if _VIDEO_ID.fullmatch(video_id) is None:
        return None
    english = _caption_text(_get_timedtext(f"{_TIMEDTEXT}?v={video_id}&lang=en"))
    if english:
        return english
    listing = _get_timedtext(f"{_TIMEDTEXT}?type=list&v={video_id}")
    language = _first_language(listing)
    if language is None:
        return None
    return _caption_text(_get_timedtext(f"{_TIMEDTEXT}?v={video_id}&lang={language}"))


def youtube_id(url: str) -> str | None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in _YOUTUBE_HOSTS:
        return None
    if host == "youtu.be":
        part = parsed.path.strip("/").split("/")[0]
        return part if _VIDEO_ID.fullmatch(part) else None
    if parsed.path == "/watch":
        values = parse_qs(parsed.query).get("v", [])
        if len(values) != 1 or _VIDEO_ID.fullmatch(values[0]) is None:
            return None
        return values[0]
    for prefix in ("/embed/", "/shorts/", "/v/"):
        if parsed.path.startswith(prefix):
            part = parsed.path[len(prefix) :].split("/")[0]
            return part if _VIDEO_ID.fullmatch(part) else None
    return None


def _store(
    root: Path,
    *,
    url: str,
    video_id: str,
    title: str,
    transcript: str,
    transcript_origin: str,
    actor: dict[str, object] | None,
) -> dict[str, object]:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    record: dict[str, object] = {
        "schema_version": "1.0.0",
        "id": digest,
        "url": url,
        "video_id": video_id,
        "title": title,
        "kind": "youtube",
        "transcript": transcript,
        "transcript_origin": transcript_origin,
        "state": "DISCOVERED",
        "classification": "PENDING",
        "authority": None,
        "downloaded": False,
        "content_directives_ignored": contains_directive(transcript.encode("utf-8")),
        "recorded_at": utc_now(),
    }
    try:
        with project_lock(root):
            state = load_state_holding_lock(root)
            prior = next((item for item in fold_by_id(root / MEDIA) if item.get("id") == digest), None)
            if prior is not None and prior.get("transcript") == transcript:
                return _body(state, prior, status="already_recorded")
            append_jsonl(root / MEDIA, record)
            append_jsonl(
                root / _AUDIT,
                {
                    "schema_version": "1.0.0",
                    "timestamp": utc_now(),
                    "source_id": digest,
                    "operation": "record_media",
                    "origin": transcript_origin,
                    "actor": {"kind": actor.get("kind")} if isinstance(actor, dict) and isinstance(actor.get("kind"), str) else None,
                    "previous_hash": None,
                    "new_hash": hashlib.sha256(transcript.encode("utf-8")).hexdigest(),
                    "result": "recorded",
                    "tool": "media_record",
                },
            )
            fresh = load_state_holding_lock(root)
            return _body(fresh, record, status="recorded")
    except ProjectLocked:
        return _error("storage.locked", "project is locked")


def _get_timedtext(url: str) -> bytes | None:
    if not url.startswith(f"{_TIMEDTEXT}?"):
        return None
    opener = urllib.request.build_opener(urllib.request.HTTPHandler, urllib.request.HTTPSHandler)
    request = urllib.request.Request(url, method="GET")
    try:
        with opener.open(request, timeout=10) as response:
            final = response.geturl()
            if not str(final).startswith(f"{_TIMEDTEXT}?"):
                return None
            return response.read(500_000)
    except (OSError, urllib.error.URLError, ValueError):
        return None


def _caption_text(payload: bytes | None) -> str | None:
    if not payload or b"<text" not in payload:
        return None
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return None
    parts = [unescape(node.text).strip() for node in root.iter("text") if node.text and node.text.strip()]
    cleaned = " ".join(parts).strip()
    if not cleaned or len(cleaned) > _MAX_TEXT:
        return None
    return cleaned


def _first_language(payload: bytes | None) -> str | None:
    if not payload:
        return None
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return None
    for node in root.iter("track"):
        language = node.attrib.get("lang_code")
        if isinstance(language, str) and re.fullmatch(r"[A-Za-z-]{2,12}", language):
            return language
    return None


def _body(state: dict[str, object], record: dict[str, object], *, status: str) -> dict[str, object]:
    visible = {
        "id": record.get("id"),
        "url": record.get("url"),
        "video_id": record.get("video_id"),
        "title": record.get("title"),
        "kind": "youtube",
        "transcript": record.get("transcript"),
        "transcript_origin": record.get("transcript_origin"),
        "state": "DISCOVERED",
        "classification": "PENDING",
        "authority": None,
        "downloaded": False,
    }
    if record.get("content_directives_ignored") is True:
        visible["content_directives_ignored"] = True
    return {
        "status": status,
        "media": visible,
        "downloaded": False,
        "local_sources": _local(state),
        "project_state": state.get("state"),
        "released": state.get("state") == "RELEASED",
    }


def _http_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned.startswith(("http://", "https://")) or any(character.isspace() for character in cleaned):
        return None
    return cleaned


def _video_file(url: str) -> bool:
    lowered = url.lower()
    return "videoplayback" in lowered or "googlevideo" in lowered or lowered.endswith((".mp4", ".webm", ".mkv"))


def _title(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or len(cleaned) > 500:
        return None
    return cleaned


def _transcript(value: object) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    if not isinstance(value, str):
        return None, "transcript must be text the client extracted"
    cleaned = value.strip()
    if not cleaned:
        return None, None
    if len(cleaned) > _MAX_TEXT:
        return None, "transcript is too long to store"
    return cleaned, None


def _local(state: dict[str, object]) -> dict[str, object]:
    local = state.get("local_sources")
    if isinstance(local, dict):
        return dict(local)
    return {"status": "UNKNOWN", "prompted": False, "source_count": 0}


def _error(code: str, message: str) -> dict[str, object]:
    return {"status": code, "message": message, "downloaded": False}
