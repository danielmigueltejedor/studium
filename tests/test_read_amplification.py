"""F30: checking many paragraphs must not re-read every record file once per paragraph."""

import studium.storage.records as records
from studium.authoring.audit import audited_paragraph_ids, review_blockers
from studium.authoring.paragraphs import supported_paragraphs
from studium.mcp.server import dispatch, open_workspace


def _explode(*_args, **_kwargs):
    raise RuntimeError("network access not allowed in tests")


def _book(tmp_path, monkeypatch, count: int):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    (tmp_path / "ws").mkdir(parents=True)
    session = open_workspace(str(tmp_path / "ws"))
    assert dispatch("studium_project_create", {"slug": "b", "topic": "Fluidos", "language": "es"}, session=session)["status"] == "created"
    assert dispatch("studium_blueprint_store", {"sections": [{"id": "s1", "title": "Uno"}]}, session=session)["status"] == "recorded"
    excerpts = []
    for index in range(2):
        url = f"https://open.example/{index}"
        source = dispatch("studium_public_source_record", {"title": f"Page {index}", "url": url}, session=session)
        excerpt = dispatch(
            "studium_excerpt_record",
            {"source_id": source["candidate"]["id"], "url": url, "text": f"An opened page {index} states a stored fact."},
            session=session,
        )
        excerpts.append(excerpt["excerpt"]["id"])
    for index in range(count):
        recorded = dispatch(
            "studium_paragraph_record",
            {"section": "s1", "text": f"Párrafo {index} con una explicación suficiente para el lector.", "excerpts": excerpts},
            session=session,
        )
        assert recorded["status"] == "recorded", recorded
    return tmp_path / "ws" / "b"


def _reads(monkeypatch, call) -> int:
    counter = {"reads": 0}
    original = records.read_jsonl

    def counting(path):
        counter["reads"] += 1
        return original(path)

    monkeypatch.setattr(records, "read_jsonl", counting)
    call()
    monkeypatch.setattr(records, "read_jsonl", original)
    return counter["reads"]


def test_supported_paragraphs_reads_each_file_once_whatever_the_book_size(tmp_path, monkeypatch):
    small = _book(tmp_path / "small", monkeypatch, 3)
    large = _book(tmp_path / "large", monkeypatch, 30)
    small_reads = _reads(monkeypatch, lambda: supported_paragraphs(small))
    large_reads = _reads(monkeypatch, lambda: supported_paragraphs(large))
    assert len(supported_paragraphs(large)) == 30
    assert large_reads == small_reads <= 5


def test_review_and_audit_coverage_reads_do_not_grow_with_paragraphs(tmp_path, monkeypatch):
    small = _book(tmp_path / "small", monkeypatch, 3)
    large = _book(tmp_path / "large", monkeypatch, 30)
    for call in (audited_paragraph_ids, review_blockers):
        small_reads = _reads(monkeypatch, lambda call=call: call(small))
        large_reads = _reads(monkeypatch, lambda call=call: call(large))
        assert large_reads == small_reads, call.__name__
