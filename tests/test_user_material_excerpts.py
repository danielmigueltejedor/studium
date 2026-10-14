"""Excerpts quoted from user-provided files: provenance is checked, truth is not."""

import io
import json
import shutil
import zipfile

import pytest

from studium.authoring.render import render_draft
from studium.authoring.support import corroboration_for_excerpts, paragraph_citation_blockers
from studium.mcp.server import dispatch, open_workspace

_PRIVATE = "PRIVATE_MARKER_7c1e: el resto de los apuntes no debe copiarse al proyecto."
_QUOTE = "El método de las fuerzas toma como incógnitas las reacciones hiperestáticas."


def _explode(*_args, **_kwargs):
    raise RuntimeError("network access not allowed in tests")


def _book(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    (tmp_path / "ws").mkdir()
    session = open_workspace(str(tmp_path / "ws"))
    assert session is not None
    created = dispatch(
        "studium_project_create",
        {"slug": "estructuras", "course": "Teoría de Estructuras", "university": "ULE", "degree": "Aero", "language": "es", "profile": "STEM"},
        session=session,
    )
    assert created["status"] == "created", created
    assert dispatch("studium_blueprint_store", {"sections": [{"id": "t1", "title": "Tema 1"}]}, session=session)["status"] == "recorded"
    return session, tmp_path / "ws" / "estructuras"


def _intake(session, path):
    imported = dispatch("studium_source_intake", {"path": str(path)}, session=session)
    assert imported["status"] == "imported", imported
    return imported["sources"][0]["id"]


def _notes(tmp_path, name="apuntes-tema1.md", body=None):
    folder = tmp_path / "materiales"
    folder.mkdir(exist_ok=True)
    path = folder / name
    path.write_text(body or f"# Tema 1\n\n{_QUOTE}\n\n{_PRIVATE}\n", encoding="utf-8")
    return path


def _excerpt(session, source_id, path, text=_QUOTE, **extra):
    return dispatch(
        "studium_excerpt_record",
        {"source_id": source_id, "path": str(path), "text": text, "locator": "Tema 1, apartado 1.2", **extra},
        session=session,
    )


def _public_excerpt(session, url, text):
    source = dispatch("studium_public_source_record", {"title": "Open page", "url": url, "text": text}, session=session)
    source_id = source["candidate"]["id"]
    dispatch("studium_public_source_open_supplement", {"id": source_id, "open_supplement": True, "open_licensed": True}, session=session)
    excerpt = dispatch("studium_excerpt_record", {"source_id": source_id, "url": url, "text": text}, session=session)
    assert excerpt["status"] == "recorded", excerpt
    return excerpt["excerpt"]["id"]


def _project_text(root):
    return "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in root.rglob("*") if path.is_file())


def test_quote_found_in_the_registered_file_is_stored_with_provenance(tmp_path, monkeypatch):
    session, root = _book(tmp_path, monkeypatch)
    path = _notes(tmp_path)
    source_id = _intake(session, path)
    recorded = _excerpt(session, source_id, path)
    assert recorded["status"] == "recorded", recorded
    excerpt = recorded["excerpt"]
    assert excerpt["source_id"] == source_id
    assert excerpt["source_kind"] == "local"
    assert excerpt["locator"] == "Tema 1, apartado 1.2"
    assert excerpt["quote_check"]["status"] == "found_in_file"
    assert excerpt["classification"] == "PENDING" and excerpt["authority"] is None
    stored = _project_text(root)
    # The quote is stored; the rest of the file and the path are not.
    assert _QUOTE in stored
    assert "PRIVATE_MARKER_7c1e" not in stored
    assert str(path.parent) not in stored
    again = _excerpt(session, source_id, path)
    assert again["status"] == "already_recorded"


def test_quote_not_in_the_file_is_rejected(tmp_path, monkeypatch):
    session, _root = _book(tmp_path, monkeypatch)
    path = _notes(tmp_path)
    source_id = _intake(session, path)
    rejected = _excerpt(session, source_id, path, text="El método de los desplazamientos es siempre más rápido.")
    assert rejected["status"] == "excerpt.not_in_source", rejected


def test_whitespace_hyphenation_and_typography_do_not_hide_a_verbatim_quote(tmp_path, monkeypatch):
    session, _root = _book(tmp_path, monkeypatch)
    body = "El mé-\ntodo de las fuerzas toma como “incógnitas” las\nreacciones   hiperestáticas.\n"
    path = _notes(tmp_path, body=body)
    source_id = _intake(session, path)
    recorded = _excerpt(session, source_id, path, text='El método de las fuerzas toma como "incógnitas" las reacciones hiperestáticas.')
    assert recorded["status"] == "recorded", recorded


def test_a_different_file_at_the_path_is_not_the_registered_source(tmp_path, monkeypatch):
    session, _root = _book(tmp_path, monkeypatch)
    path = _notes(tmp_path)
    source_id = _intake(session, path)
    path.write_text(f"{_QUOTE}\nversión editada\n", encoding="utf-8")
    rejected = _excerpt(session, source_id, path)
    assert rejected["status"] == "sources.hash_mismatch", rejected


def test_locator_and_path_are_required(tmp_path, monkeypatch):
    session, _root = _book(tmp_path, monkeypatch)
    path = _notes(tmp_path)
    source_id = _intake(session, path)
    no_locator = dispatch("studium_excerpt_record", {"source_id": source_id, "path": str(path), "text": _QUOTE}, session=session)
    assert no_locator["status"] == "mcp.invalid_input" and "locator" in no_locator["message"]
    no_path = dispatch("studium_excerpt_record", {"source_id": source_id, "text": _QUOTE, "locator": "p. 1"}, session=session)
    assert no_path["status"] == "mcp.invalid_input" and "path" in no_path["message"]


def test_paragraph_may_cite_user_material_but_two_user_files_are_one_witness(tmp_path, monkeypatch):
    session, root = _book(tmp_path, monkeypatch)
    first = _notes(tmp_path, "tema1.md")
    second = _notes(tmp_path, "tema1-bis.md", body=f"Copia de clase.\n{_QUOTE}\n")
    first_id, second_id = _intake(session, first), _intake(session, second)
    left = _excerpt(session, first_id, first)["excerpt"]["id"]
    right = _excerpt(session, second_id, second)["excerpt"]["id"]
    assert paragraph_citation_blockers(root, [left]) == []
    paragraph = dispatch(
        "studium_paragraph_record",
        {"section": "t1", "text": "El método de las fuerzas elige las reacciones hiperestáticas como incógnitas.", "excerpts": [left]},
        session=session,
    )
    assert paragraph["status"] == "recorded", paragraph
    assert corroboration_for_excerpts(root, [left, right]) is None
    public = _public_excerpt(session, "https://open.example/fuerzas", "The force method takes the redundant reactions as unknowns.")
    assert corroboration_for_excerpts(root, [left, public]) == "two_witnesses"


def test_rejected_or_removed_source_no_longer_supports_a_draft(tmp_path, monkeypatch):
    session, root = _book(tmp_path, monkeypatch)
    path = _notes(tmp_path)
    source_id = _intake(session, path)
    excerpt_id = _excerpt(session, source_id, path)["excerpt"]["id"]
    rejected = dispatch("studium_source_reject", {"source_id": source_id, "reason": "notas de otro curso"}, session=session)
    assert rejected["status"] in {"ok", "rejected"}, rejected
    blockers = paragraph_citation_blockers(root, [excerpt_id])
    assert [item["code"] for item in blockers] == ["claim.source_rejected"]


def test_bibliography_names_the_file_as_private_unverified_material(tmp_path, monkeypatch):
    session, root = _book(tmp_path, monkeypatch)
    path = _notes(tmp_path, "Apuntes Tema 1.md")
    source_id = _intake(session, path)
    excerpt_id = _excerpt(session, source_id, path)["excerpt"]["id"]
    dispatch(
        "studium_paragraph_record",
        {"section": "t1", "text": "El método de las fuerzas elige las reacciones hiperestáticas como incógnitas.", "excerpts": [excerpt_id]},
        session=session,
    )
    render_draft(root)
    tex = (root / "latex" / "draft.tex").read_text(encoding="utf-8")
    bibliography = tex[tex.index(r"\begin{thebibliography}") :]
    assert "Apuntes Tema 1.md. Material aportado por el usuario (privado; no verificado)." in bibliography
    assert str(path.parent) not in tex


def _docx(path, paragraphs):
    document = "".join(f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>" for text in paragraphs)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
        + document
        + "</w:body></w:document>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", xml)
    path.write_bytes(buffer.getvalue())


def test_docx_text_is_checked(tmp_path, monkeypatch):
    session, _root = _book(tmp_path, monkeypatch)
    folder = tmp_path / "materiales"
    folder.mkdir()
    path = folder / "practica.docx"
    _docx(path, ["Práctica 2", _QUOTE])
    source_id = _intake(session, path)
    assert _excerpt(session, source_id, path)["status"] == "recorded"


def _pdf(path, pages):
    """A minimal PDF with one Helvetica text line per page."""

    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", None, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for text in pages:
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
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))


@pytest.mark.skipif(shutil.which("pdftotext") is None, reason="needs pdftotext")
def test_pdf_quote_is_checked_on_the_stated_page(tmp_path, monkeypatch):
    session, root = _book(tmp_path, monkeypatch)
    folder = tmp_path / "materiales"
    folder.mkdir()
    path = folder / "tema3.pdf"
    _pdf(path, ["Tema 3. Vigas continuas.", "La matriz de rigidez es simetrica y definida positiva."])
    source_id = _intake(session, path)
    quote = "La matriz de rigidez es simetrica y definida positiva."
    wrong = _excerpt(session, source_id, path, text=quote, page=1)
    assert wrong["status"] == "excerpt.not_in_source", wrong
    assert "page(s) 2" in wrong["message"]
    right = _excerpt(session, source_id, path, text=quote, page=2)
    assert right["status"] == "recorded", right
    assert right["excerpt"]["quote_check"] == {"status": "found_in_file", "method": "pdftotext", "page_checked": True, "pages": [2]}
    listed = dispatch("studium_excerpt_list", {}, session=session)
    assert json.dumps(listed).count("tema3.pdf") == 0
    assert "Vigas continuas" not in _project_text(root)
