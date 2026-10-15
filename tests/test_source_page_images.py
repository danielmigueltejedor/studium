"""Image-only pages of user PDFs: look at the page, record a client transcription, ground nothing with it."""

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from studium.authoring.grounding import equation_evidence
from studium.mcp.server import dispatch, open_workspace

pytestmark = pytest.mark.skipif(
    shutil.which("pdftoppm") is None or shutil.which("pdftotext") is None or shutil.which("pdfinfo") is None,
    reason="needs poppler",
)

_EQUATION = r"\delta = \frac{P L^{3}}{3 E I}"


def _explode(*_args, **_kwargs):
    raise RuntimeError("network access not allowed in tests")


def _pdf(path: Path, pages: list[str | None]) -> None:
    """A PDF whose page is a Helvetica text line, or only drawn lines (like a scanned slide) when ``None``."""

    objects: list[bytes | None] = [b"<< /Type /Catalog /Pages 2 0 R >>", None, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for text in pages:
        if text is None:
            stream = b"2 w 100 100 400 300 re S 100 100 m 500 400 l S 100 400 m 500 100 l S"
        else:
            stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
        objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
        content = len(objects)
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {content} 0 R /Resources << /Font << /F1 3 0 R >> >> >>".encode()
        )
        kids.append(len(objects))
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(f'{kid} 0 R' for kid in kids)}] /Count {len(kids)} >>".encode()
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + (body or b"") + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))


def _book(tmp_path, monkeypatch, pages):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    (tmp_path / "ws").mkdir()
    session = open_workspace(str(tmp_path / "ws"))
    assert session is not None
    created = dispatch(
        "studium_project_create",
        {"slug": "est", "course": "Teoría de Estructuras", "university": "ULE", "degree": "Aero", "language": "es", "profile": "STEM"},
        session=session,
    )
    assert created["status"] == "created", created
    assert dispatch("studium_blueprint_store", {"sections": [{"id": "t1", "title": "Tema 1"}]}, session=session)["status"] == "recorded"
    folder = tmp_path / "materiales"
    folder.mkdir()
    pdf = folder / "diapositivas.pdf"
    _pdf(pdf, pages)
    imported = dispatch("studium_source_intake", {"path": str(pdf)}, session=session)
    assert imported["status"] == "imported", imported
    return session, tmp_path / "ws" / "est", pdf, imported["sources"][0]["id"]


def test_page_image_is_rendered_outside_the_project_and_tied_to_the_registered_file(tmp_path, monkeypatch):
    session, root, pdf, source_id = _book(tmp_path, monkeypatch, ["Portada del tema", None])
    result = dispatch("studium_source_page_image", {"source_id": source_id, "path": str(pdf), "page": 2}, session=session)
    assert result["status"] == "ok", result
    image = Path(result["image_path"])
    assert image.is_file() and image.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert hashlib.sha256(image.read_bytes()).hexdigest() == result["image_sha256"]
    assert result["pages"] == 2 and result["page"] == 2 and result["dpi"] == 110
    assert result["width"] > 400 and result["height"] > 500
    assert root not in image.parents and tmp_path / "materiales" not in image.parents
    assert str(image) not in "\n".join(path.read_text(errors="ignore") for path in root.rglob("*") if path.is_file())
    again = dispatch("studium_source_page_image", {"source_id": source_id, "path": str(pdf), "page": 2}, session=session)
    assert again["image_sha256"] == result["image_sha256"]


def test_page_image_rejects_a_changed_file_a_bad_page_and_a_bad_dpi(tmp_path, monkeypatch):
    session, _root, pdf, source_id = _book(tmp_path, monkeypatch, ["Portada del tema", None])
    past = dispatch("studium_source_page_image", {"source_id": source_id, "path": str(pdf), "page": 3}, session=session)
    assert past["status"] == "mcp.invalid_input" and "2 pages" in past["message"]
    low = dispatch("studium_source_page_image", {"source_id": source_id, "path": str(pdf), "page": 1, "dpi": 10}, session=session)
    assert low["status"] == "mcp.invalid_input"
    other = tmp_path / "otra.pdf"
    _pdf(other, ["Otro documento", None])
    changed = dispatch("studium_source_page_image", {"source_id": source_id, "path": str(other), "page": 1}, session=session)
    assert changed["status"] == "sources.hash_mismatch", changed


def test_an_image_only_page_needs_the_transcription_flag(tmp_path, monkeypatch):
    session, root, pdf, source_id = _book(tmp_path, monkeypatch, ["Portada del tema", None])
    plain = dispatch(
        "studium_excerpt_record",
        {"source_id": source_id, "path": str(pdf), "text": f"La flecha es ${_EQUATION}$ en el extremo libre.", "locator": "diapositiva 2", "page": 2},
        session=session,
    )
    assert plain["status"] == "excerpt.not_in_source", plain
    assert "transcribed_from_image" in plain["message"]
    recorded = dispatch(
        "studium_excerpt_record",
        {
            "source_id": source_id,
            "path": str(pdf),
            "text": f"La flecha es ${_EQUATION}$ en el extremo libre.",
            "locator": "diapositiva 2",
            "page": 2,
            "transcribed_from_image": True,
        },
        session=session,
    )
    assert recorded["status"] == "recorded", recorded
    check = recorded["excerpt"]["quote_check"]
    assert check["status"] == "client_transcription" and check["verified"] is False
    assert check["pages"] == [2] and len(check["page_image_sha256"]) == 64
    image = dispatch("studium_source_page_image", {"source_id": source_id, "path": str(pdf), "page": 2}, session=session)
    assert check["page_image_sha256"] == image["image_sha256"]
    # The words are stored; the page image and the path are not.
    stored = "\n".join(path.read_text(errors="ignore") for path in root.rglob("*") if path.is_file())
    assert json.dumps(_EQUATION)[1:-1] in stored and str(pdf.parent) not in stored
    again = dispatch(
        "studium_excerpt_record",
        {
            "source_id": source_id,
            "path": str(pdf),
            "text": f"La flecha es ${_EQUATION}$ en el extremo libre.",
            "locator": "diapositiva 2",
            "page": 2,
            "transcribed_from_image": True,
        },
        session=session,
    )
    assert again["status"] == "already_recorded"


def test_a_transcribed_equation_is_never_source_supported(tmp_path, monkeypatch):
    session, root, pdf, source_id = _book(tmp_path, monkeypatch, ["Portada del tema", None])
    excerpt = dispatch(
        "studium_excerpt_record",
        {
            "source_id": source_id,
            "path": str(pdf),
            "text": f"La flecha es ${_EQUATION}$ en el extremo libre.",
            "locator": "diapositiva 2",
            "page": 2,
            "transcribed_from_image": True,
        },
        session=session,
    )["excerpt"]["id"]
    paragraph = dispatch(
        "studium_paragraph_record",
        {"section": "t1", "text": f"La flecha en el extremo libre de la ménsula vale ${_EQUATION}$ según la diapositiva.", "excerpts": [excerpt]},
        session=session,
    )
    assert paragraph["status"] == "recorded", paragraph
    items = equation_evidence(root, paragraph["paragraph"])
    assert [item["status"] for item in items] == ["unsupported"]
    assert items[0]["human_review"] == "required"


def test_the_flag_is_checked_and_a_text_layer_quote_needs_no_transcription(tmp_path, monkeypatch):
    session, _root, pdf, source_id = _book(tmp_path, monkeypatch, ["La mensula es una viga empotrada en un extremo", None])
    no_page = dispatch(
        "studium_excerpt_record",
        {"source_id": source_id, "path": str(pdf), "text": "algo", "locator": "x", "transcribed_from_image": True},
        session=session,
    )
    assert no_page["status"] == "mcp.invalid_input", no_page
    past = dispatch(
        "studium_excerpt_record",
        {"source_id": source_id, "path": str(pdf), "text": "algo", "locator": "x", "page": 9, "transcribed_from_image": True},
        session=session,
    )
    assert past["status"] == "mcp.invalid_input" and "2 pages" in past["message"]
    found = dispatch(
        "studium_excerpt_record",
        {
            "source_id": source_id,
            "path": str(pdf),
            "text": "La mensula es una viga empotrada en un extremo",
            "locator": "diapositiva 1",
            "page": 1,
            "transcribed_from_image": True,
        },
        session=session,
    )
    assert found["status"] == "recorded", found
    assert found["excerpt"]["quote_check"]["status"] == "found_in_file"
