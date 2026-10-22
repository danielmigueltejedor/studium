"""Pictures from open sources keep their author, page and licence, and render with them."""

import hashlib
import shutil
import struct
import zlib

import pytest
from test_render_regression import _excerpts, _explode, _project

from studium.authoring.figure_images import dimensions, image_format, normalise_license
from studium.authoring.render import render_draft
from studium.mcp.server import dispatch


def _png(width=320, height=240, colour=b"\xc8\x32\x32"):
    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + colour * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


_IMAGE = {
    "path": "figures/incoming/mapa.png",
    "url": "https://commons.wikimedia.org/wiki/File:Mapa.png",
    "title": "Mapa de la Monarquía Hispánica",
    "author": "Ejemplo Autor",
    "license": "CC BY-SA 4.0",
}


def _book(tmp_path, monkeypatch, data=None):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _project(tmp_path, profile="HUMANITIES")
    dispatch("studium_blueprint_store", {"sections": [{"id": "mapa", "title": "El mapa"}]}, session=session)
    excerpts = _excerpts(session)
    dispatch(
        "studium_paragraph_record",
        {"section": "mapa", "text": "La Monarquía reunió territorios muy distintos.", "excerpts": excerpts},
        session=session,
    )
    incoming = root / "figures" / "incoming"
    incoming.mkdir(parents=True)
    (incoming / "mapa.png").write_bytes(data if data is not None else _png())
    return session, root, excerpts


def _record(session, **extra):
    arguments = {
        "section": "mapa",
        "caption": "Territorios de la Monarquía Hispánica.",
        "kind": "image",
        "image": _IMAGE,
        "excerpts": [],
        "key": "mapa",
    } | extra
    return dispatch("studium_figure_record", arguments, session=session)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("CC BY-SA 4.0", "CC BY-SA 4.0"),
        ("cc-by-sa-3.0", "CC BY-SA 3.0"),
        ("CC BY 2.5", "CC BY 2.5"),
        ("CC0", "CC0 1.0"),
        ("Public domain", "Public domain"),
        ("Dominio público", "Public domain"),
        ("PD-old-100", "Public domain"),
    ],
)
def test_open_licences_are_normalised(text, expected):
    assert normalise_license(text)[0] == expected


@pytest.mark.parametrize("text", ["CC BY-NC 4.0", "CC BY-ND 4.0", "GFDL", "All rights reserved", "CC BY-SA 9.9", "", None])
def test_other_licences_are_refused(text):
    assert normalise_license(text) is None


def test_the_header_gives_format_and_size():
    data = _png(321, 123)
    assert image_format(data) == "png" and dimensions(data, "png") == (321, 123)
    assert image_format(b"GIF89a....") is None


def test_an_image_figure_is_recorded_and_checked(tmp_path, monkeypatch):
    session, root, excerpts = _book(tmp_path, monkeypatch)
    stored = _record(session, excerpts=excerpts)
    assert stored["status"] == "recorded", stored
    figure = stored["figure"]
    assert figure["kind"] == "image" and figure["image"]["license"] == "CC BY-SA 4.0"
    checked = dispatch("studium_figure_check", {"id": figure["id"]}, session=session)
    assert checked["status"] == "checked", checked
    assert checked["figure"]["output"].endswith("/figure.png")
    assert (root / checked["figure"]["output"]).read_bytes() == _png()


def test_a_licence_that_is_not_open_is_refused(tmp_path, monkeypatch):
    session, _root, excerpts = _book(tmp_path, monkeypatch)
    refused = _record(session, excerpts=excerpts, image=_IMAGE | {"license": "CC BY-NC 4.0"})
    assert refused["status"] == "figure.license_not_allowed", refused


@pytest.mark.parametrize("drop", ["author", "title", "url"])
def test_an_image_needs_author_title_and_page(tmp_path, monkeypatch, drop):
    session, _root, excerpts = _book(tmp_path, monkeypatch)
    refused = _record(session, excerpts=excerpts, image={k: v for k, v in _IMAGE.items() if k != drop})
    assert refused["status"] == "mcp.invalid_input", refused


def test_the_file_must_be_a_real_picture_inside_the_book(tmp_path, monkeypatch):
    session, root, excerpts = _book(tmp_path, monkeypatch)
    outside = _record(session, excerpts=excerpts, image=_IMAGE | {"path": "../outside.png"})
    assert outside["status"] == "figure.path_escaped", outside
    missing = _record(session, excerpts=excerpts, image=_IMAGE | {"path": "figures/incoming/none.png"})
    assert missing["status"] == "figure.image_missing", missing
    (root / "figures/incoming/mapa.png").write_bytes(b"not a picture at all" * 20)
    assert _record(session, excerpts=excerpts)["status"] == "figure.image_invalid"
    (root / "figures/incoming/mapa.png").write_bytes(_png(40, 40))
    assert _record(session, excerpts=excerpts)["status"] == "figure.image_invalid"


def test_an_image_figure_takes_no_executable_source(tmp_path, monkeypatch):
    session, _root, excerpts = _book(tmp_path, monkeypatch)
    refused = _record(session, excerpts=excerpts, source=r"\draw (0,0)--(1,1);")
    assert refused["status"] == "mcp.invalid_input"
    other = _record(session, excerpts=excerpts, kind="tikz", source=r"\draw (0,0)--(1,1);")
    assert other["status"] == "mcp.invalid_input"


def test_a_file_changed_after_recording_is_not_checked(tmp_path, monkeypatch):
    session, root, excerpts = _book(tmp_path, monkeypatch)
    figure = _record(session, excerpts=excerpts)["figure"]
    (root / "figures/incoming/mapa.png").write_bytes(_png(400, 300, b"\x00\x00\x00"))
    checked = dispatch("studium_figure_check", {"id": figure["id"]}, session=session)
    assert checked["status"] == "unchecked" and "changed since" in checked["message"]
    assert "output" not in checked["figure"]


@pytest.mark.skipif(not (shutil.which("pdflatex") and shutil.which("pdftotext")), reason="needs pdflatex and pdftotext")
def test_the_picture_prints_with_its_credit_and_is_listed_once_more_at_the_end(tmp_path, monkeypatch):
    session, root, excerpts = _book(tmp_path, monkeypatch)
    figure = _record(session, excerpts=excerpts)["figure"]
    assert dispatch("studium_figure_check", {"id": figure["id"]}, session=session)["status"] == "checked"
    render_draft(root)
    tex = (root / "latex" / "draft.tex").read_text(encoding="utf-8")
    assert r"\includegraphics{../figures/" + figure["id"] + "/figure.png}" in tex
    assert "Ejemplo Autor" in tex and "CC BY-SA 4.0" in tex and "commons.wikimedia.org" in tex
    assert tex.count("Ejemplo Autor") == 2
    assert r"\chapter*{Créditos de las figuras}" in tex


def test_a_book_without_pictures_gets_no_credits_chapter(tmp_path, monkeypatch):
    _session, root, _unused = _book(tmp_path, monkeypatch)
    render_draft(root)
    assert "Créditos de las figuras" not in (root / "latex" / "draft.tex").read_text(encoding="utf-8")


def test_the_stored_record_keeps_the_file_hash(tmp_path, monkeypatch):
    session, root, excerpts = _book(tmp_path, monkeypatch)
    assert _record(session, excerpts=excerpts)["status"] == "recorded"
    stored = (root / "figures.jsonl").read_text(encoding="utf-8") if (root / "figures.jsonl").exists() else ""
    if not stored:
        stored = "".join(path.read_text(encoding="utf-8") for path in root.rglob("figures*.jsonl"))
    assert hashlib.sha256(_png()).hexdigest() in stored
