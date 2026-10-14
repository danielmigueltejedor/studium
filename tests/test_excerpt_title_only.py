"""An excerpt that only repeats the source title is not evidence."""

from studium.mcp.server import dispatch, open_workspace


def _source(tmp_path):
    session = open_workspace(str(tmp_path))
    dispatch("studium_project_create", {"slug": "t", "topic": "Thermodynamics", "language": "en", "profile": "STEM"}, session=session)
    session = open_workspace(str(tmp_path), str(tmp_path / "t"))
    url = "https://open.example/first-law"
    source = dispatch("studium_public_source_record", {"title": "OpenStax 3.3 First Law", "url": url}, session=session)
    return session, source["candidate"]["id"], url


def test_title_only_excerpt_is_rejected(tmp_path):
    session, source_id, url = _source(tmp_path)
    for text in ("OpenStax 3.3 First Law", "  openstax 3.3: FIRST law. "):
        result = dispatch("studium_excerpt_record", {"source_id": source_id, "url": url, "text": text}, session=session)
        assert result["status"] == "excerpt.title_only", result
    assert dispatch("studium_excerpt_list", {}, session=session)["excerpts"] == []


def test_passage_that_mentions_the_title_is_accepted(tmp_path):
    session, source_id, url = _source(tmp_path)
    text = "OpenStax 3.3 First Law: the change in internal energy equals Q minus W."
    result = dispatch("studium_excerpt_record", {"source_id": source_id, "url": url, "text": text}, session=session)
    assert result["status"] == "recorded", result
