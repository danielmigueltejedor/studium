"""Atomic records, interrupted writes, and stale dependent results."""

import threading
from pathlib import Path

from studium.authoring.audit import audited_paragraph_ids, review_is_current
from studium.authoring.problems import problem_result_current
from studium.mcp.server import dispatch, open_workspace
from studium.storage.locking import ProjectLocked, project_lock
from studium.storage.records import RecordCorruption, append_jsonl, read_jsonl

_TEACH = (
    "This explanation teaches the stored quantity so a reader can follow the derivation, "
    "the comparison, and the later problem without treating the model as a source of truth."
)


def test_trailing_partial_line_is_recovered_and_middle_corruption_fails(tmp_path):
    path = tmp_path / "records.jsonl"
    append_jsonl(path, {"id": "A", "text": "kept"})
    with path.open("ab") as handle:
        handle.write(b'{"id":"B","text":"cut')
    rows = read_jsonl(path)
    assert rows == [{"id": "A", "text": "kept"}]
    append_jsonl(path, {"id": "C", "text": "after"})
    damaged = path.read_bytes().replace(b'"C"', b'"C"', 1)
    path.write_bytes(b'{"id":"A"}\nnot-json\n{"id":"C"}\n')
    try:
        read_jsonl(path)
    except RecordCorruption as exc:
        assert exc.lines == [2]
    else:
        raise AssertionError("middle corruption was accepted")
    assert damaged


def test_concurrent_lock_does_not_interleave_records(tmp_path):
    from studium.mcp.server import dispatch as create_dispatch

    session = open_workspace(str(tmp_path))
    created = create_dispatch(
        "studium_project_create",
        {"slug": "fluidos", "topic": "Mecánica de fluidos"},
        session=session,
    )
    root = Path(created["path"])
    path = root / "draft" / "notes.jsonl"
    errors: list[str] = []

    def writer(mark: str) -> None:
        try:
            with project_lock(root):
                append_jsonl(path, {"id": mark, "text": mark * 40})
        except ProjectLocked:
            errors.append(mark)

    first = threading.Thread(target=writer, args=("one",))
    second = threading.Thread(target=writer, args=("two",))
    first.start()
    second.start()
    first.join()
    second.join()
    rows = read_jsonl(path)
    assert {row["id"] for row in rows} | set(errors) == {"one", "two"}
    for row in rows:
        assert row["text"] == str(row["id"]) * 40


def test_changed_source_and_exercise_do_not_keep_a_stale_result(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session = open_workspace(str(tmp_path))
    assert dispatch(
        "studium_project_create",
        {"slug": "historia", "topic": "Historia medieval"},
        session=session,
    )["status"] == "created"
    root = tmp_path / "historia"
    dispatch(
        "studium_blueprint_store",
        {"sections": [{"id": "tema-1", "title": "Origenes"}]},
        session=session,
    )
    left_source = dispatch(
        "studium_public_source_record",
        {"title": "Open page", "url": "https://open.example/one", "text": "The density is 2."},
        session=session,
    )
    right_source = dispatch(
        "studium_public_source_record",
        {"title": "Other page", "url": "https://open.example/two", "text": "The density is 2."},
        session=session,
    )
    left = dispatch(
        "studium_excerpt_record",
        {
            "source_id": left_source["candidate"]["id"],
            "url": "https://open.example/one",
            "text": f"The density is 2. {_TEACH}",
        },
        session=session,
    )["excerpt"]["id"]
    right = dispatch(
        "studium_excerpt_record",
        {
            "source_id": right_source["candidate"]["id"],
            "url": "https://open.example/two",
            "text": f"The density is 2. {_TEACH}",
        },
        session=session,
    )["excerpt"]["id"]
    paragraph = dispatch(
        "studium_paragraph_record",
        {"section": "tema-1", "text": f"The density is 2. {_TEACH}", "excerpts": [left, right]},
        session=session,
    )["paragraph"]["id"]
    problem = dispatch(
        "studium_problem_record",
        {
            "section": "tema-1",
            "prompt": "What is the stored density?",
            "expected": "2",
            "excerpts": [left, right],
        },
        session=session,
    )["problem"]
    assert problem["status"] == "two_witnesses"
    computed = dispatch(
        "studium_computation_check",
        {"expression": "2 + 2", "result": 4, "section": "tema-1"},
        session=session,
    )
    assert computed["status"] == "replayed"
    audited = dispatch(
        "studium_audit_record",
        {
            "target": paragraph,
            "kind": "scientific",
            "excerpts": [left, right],
            "computation": computed["computation"]["id"],
            "problem": problem["id"],
        },
        session=session,
    )
    assert audited["status"] == "recorded"
    assert paragraph in audited_paragraph_ids(root)
    stored_problem = next(row for row in read_jsonl(root / "problems" / "problems.jsonl") if row.get("id") == problem["id"])
    assert problem_result_current(root, stored_problem) is True

    changed_excerpt = dict(next(row for row in read_jsonl(root / "bibliography" / "excerpts.jsonl") if row.get("id") == left))
    changed_excerpt["text"] = changed_excerpt["text"] + " A later opening changes the page."
    changed_excerpt["text_sha256"] = "excerpt-no-longer-the-audited-text"
    append_jsonl(root / "bibliography" / "excerpts.jsonl", changed_excerpt)
    assert paragraph not in audited_paragraph_ids(root)
    assert problem_result_current(root, stored_problem) is False
    listed = dispatch("studium_problem_list", {}, session=session)
    visible = next(item for item in listed["problems"] if item["id"] == problem["id"])
    assert visible["status"] == "stale"
    assert visible["current"] is False
    assert review_is_current(root) is False

    source = dict(next(row for row in read_jsonl(root / "bibliography" / "public.jsonl") if row.get("id") == left_source["candidate"]["id"]))
    source["text"] = "The density is 9."
    source["text_sha256"] = "source-changed"
    append_jsonl(root / "bibliography" / "public.jsonl", source)
    fresh_left = dict(next(row for row in read_jsonl(root / "bibliography" / "excerpts.jsonl") if row.get("id") == left))
    fresh_left["text_sha256"] = changed_excerpt["text_sha256"]
    # The excerpt hash is already changed. Restore the audited excerpt text and hash, then change only the source.
    original_excerpt = next(row for row in read_jsonl(root / "bibliography" / "excerpts.jsonl") if row.get("id") == left)
    restored = dict(original_excerpt)
    restored["text"] = f"The density is 2. {_TEACH}"
    from hashlib import sha256

    restored["text_sha256"] = sha256(
        f"{left_source['candidate']['id']}\nhttps://open.example/one\n{restored['text']}".encode()
    ).hexdigest()
    append_jsonl(root / "bibliography" / "excerpts.jsonl", restored)
    # Re-audit against the restored excerpt, then change the source record only.
    again = dispatch(
        "studium_audit_record",
        {"target": paragraph, "kind": "scientific", "excerpts": [left, right]},
        session=session,
    )
    assert again["status"] == "recorded"
    assert paragraph in audited_paragraph_ids(root)
    moved = dict(source)
    moved["text_sha256"] = "source-changed-again"
    append_jsonl(root / "bibliography" / "public.jsonl", moved)
    assert paragraph not in audited_paragraph_ids(root)

    exercise = dict(stored_problem)
    exercise["expected"] = "9"
    append_jsonl(root / "problems" / "problems.jsonl", exercise)
    assert problem_result_current(root, exercise) is False
    reviewed = dispatch("studium_book_review", {}, session=session)
    assert reviewed["audit_passed"] is False
    assert reviewed["released"] is False


def _explode(*_args, **_kwargs):
    raise AssertionError("must not fetch")
