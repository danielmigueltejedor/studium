"""A 'no replayed check' block lifts once a replayed computation exists."""

from studium.authoring import book_next
from studium.authoring.section_blocks import blocked_ids, mark_blocked, release_block
from studium.mcp.server import dispatch, open_workspace


def _topic(tmp_path):
    session = open_workspace(str(tmp_path))
    dispatch("studium_project_create", {"slug": "fisica", "topic": "Fisica", "language": "en"}, session=session)
    return session, tmp_path / "fisica"


def test_release_block_lifts_a_block(tmp_path):
    _session, root = _topic(tmp_path)
    assert release_block(root, section_id="a") is False
    mark_blocked(root, section_id="a", title="A", reason="no replayed check")
    assert blocked_ids(root) == {"a"}
    assert release_block(root, section_id="a") is True
    assert blocked_ids(root) == set()


def test_pending_problem_releases_block_after_replayed_computation(tmp_path, monkeypatch):
    session, root = _topic(tmp_path)
    monkeypatch.setattr(book_next, "_profile", lambda _root: "STEM")
    sections = [{"id": "a", "title": "A"}]
    mark_blocked(root, section_id="a", title="A", reason="no replayed check")
    assert book_next._pending_problem(root, sections) is None
    assert blocked_ids(root) == {"a"}
    ok = dispatch("studium_computation_check", {"expression": "1/1.2", "result": "0.833"}, session=session)
    assert ok["status"] == "replayed"
    assert book_next._pending_problem(root, sections) is None
    assert blocked_ids(root) == set()
