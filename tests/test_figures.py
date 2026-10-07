"""A figure is checked only when its stored source is run again."""

import json
from pathlib import Path

from studium.authoring.figures import figure_gap
from studium.authoring.render import find_engine
from studium.mcp.server import dispatch, handle, open_workspace, tool_names

_PNG = (
    "89504e470d0a1a0a0000000d49484452000000010000000108000000003a7e9b55"
    "0000000a49444154789c63f80f0001010100b138f6140000000049454e44ae426082"
)
_PLOT = (
    "import pathlib\n"
    f'pathlib.Path("figure.png").write_bytes(bytes.fromhex("{_PNG}"))\n'
)
_CHECKED_CAPTION = "Checked control volume from the opened page."
_NUMERIC_CAPTION = "The drawn length is 2."
_OMITTED_CAPTION = "UNCHECKED_DRAWING_CAPTION_OMITTED"


def test_passing_rerun_checks_the_figure(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _topic(tmp_path)
    excerpt_id = _ready(session)
    state_before = (root / ".studium" / "state.json").read_bytes()
    missing = dispatch(
        "studium_figure_record",
        {
            "section": "tema-1",
            "caption": _CHECKED_CAPTION,
            "kind": "python",
            "excerpts": [excerpt_id],
        },
        session=session,
    )
    assert missing["status"] == "mcp.invalid_input"
    assert missing["checked"] is False
    recorded = dispatch(
        "studium_figure_record",
        {
            "section": "tema-1",
            "caption": _CHECKED_CAPTION,
            "kind": "python",
            "source": _PLOT,
            "excerpts": [excerpt_id],
        },
        session=session,
    )
    assert recorded["status"] == "recorded"
    assert recorded["checked"] is False
    assert recorded["figure"]["id"] == "FIG-0001"
    assert recorded["figure"]["status"] == "unchecked"
    assert recorded["figure"]["proves_science"] is False
    assert recorded["released"] is False
    assert "verified" not in json.dumps(recorded)
    assert not (root / "figures" / "FIG-0001" / "figure.png").exists()
    checked = dispatch("studium_figure_check", {"id": "FIG-0001"}, session=session)
    assert checked["status"] == "checked"
    assert checked["checked"] is True
    assert checked["figure"]["correct"] is True
    assert checked["figure"]["status"] == "checked"
    assert checked["figure"]["proves_science"] is False
    assert checked["figure"]["output"] == "figures/FIG-0001/figure.png"
    assert checked["released"] is False
    assert "verified" not in json.dumps(checked)
    assert (root / "figures" / "FIG-0001" / "figure.png").is_file()
    numeric = dispatch(
        "studium_figure_record",
        {
            "section": "tema-1",
            "caption": _NUMERIC_CAPTION,
            "kind": "python",
            "source": _PLOT,
            "excerpts": [excerpt_id],
        },
        session=session,
    )
    numeric_check = dispatch("studium_figure_check", {"id": numeric["figure"]["id"]}, session=session)
    assert numeric_check["status"] == "checked"
    assert numeric_check["figure"]["caption_corroboration"] == "unchecked"
    assert numeric_check["figure"]["proves_science"] is False
    assert "verified" not in json.dumps(numeric_check)
    assert (root / ".studium" / "state.json").read_bytes() == state_before
    assert json.loads(state_before)["state"] != "RELEASED"
    assert "studium_figure_record" in tool_names()
    assert "studium_figure_check" in tool_names()
    instructions = handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})["result"]["instructions"]
    assert "A figure does not prove the science." in instructions
    source = Path("src/studium/authoring/figures.py").read_text(encoding="utf-8")
    assert "import urllib" not in source
    assert "urlopen(" not in source


def test_failing_program_stays_unchecked(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _topic(tmp_path)
    excerpt_id = _ready(session)
    dispatch(
        "studium_figure_record",
        {
            "section": "tema-1",
            "caption": "A program that does not draw.",
            "kind": "python",
            "source": "raise SystemExit(1)\n",
            "excerpts": [excerpt_id],
        },
        session=session,
    )
    state_before = (root / ".studium" / "state.json").read_bytes()
    failed = dispatch("studium_figure_check", {"id": "FIG-0001"}, session=session)
    assert failed["status"] == "unchecked"
    assert failed["checked"] is False
    assert failed["figure"]["status"] == "unchecked"
    assert failed["figure"]["correct"] is False
    assert failed["figure"]["proves_science"] is False
    assert "output" not in failed["figure"]
    assert failed["released"] is False
    assert "verified" not in json.dumps(failed)
    assert not (root / "figures" / "FIG-0001" / "figure.png").exists()
    stored = json.loads((root / "figures" / "figures.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert stored["status"] == "unchecked"
    assert stored["correct"] is False
    monkeypatch.setattr("studium.authoring.figures.shutil.which", lambda _name: None)
    missing = dispatch("studium_figure_check", {"id": "FIG-0001"}, session=session)
    assert missing["status"] == "compiler_missing"
    assert missing["checked"] is False
    assert missing["figure"]["status"] == "unchecked"
    assert "not checked" in missing["message"]
    assert (root / ".studium" / "state.json").read_bytes() == state_before
    assert json.loads(state_before)["state"] != "RELEASED"


def test_draft_omits_an_unchecked_figure(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _topic(tmp_path)
    excerpt_id = _ready(session)
    dispatch(
        "studium_paragraph_record",
        {
            "section": "tema-1",
            "text": "The opened page describes the control volume.",
            "excerpts": [excerpt_id],
        },
        session=session,
    )
    checked = dispatch(
        "studium_figure_record",
        {
            "section": "tema-1",
            "caption": _CHECKED_CAPTION,
            "kind": "python",
            "source": _PLOT,
            "excerpts": [excerpt_id],
        },
        session=session,
    )
    omitted = dispatch(
        "studium_figure_record",
        {
            "section": "tema-1",
            "caption": _OMITTED_CAPTION,
            "kind": "python",
            "source": "raise SystemExit(1)\n",
            "excerpts": [excerpt_id],
        },
        session=session,
    )
    assert dispatch("studium_figure_check", {"id": checked["figure"]["id"]}, session=session)["checked"] is True
    assert dispatch("studium_figure_check", {"id": omitted["figure"]["id"]}, session=session)["checked"] is False
    rendered = dispatch("studium_render", {}, session=session)
    tex = (root / "latex" / "draft.tex").read_text(encoding="utf-8")
    assert figure_gap(omitted["figure"]["id"]) in tex
    assert _OMITTED_CAPTION not in tex
    assert _CHECKED_CAPTION in tex
    assert r"\includegraphics" in tex
    assert checked["figure"]["id"] in tex
    assert tex.count(r"\includegraphics") == 1
    assert "A figure does not prove the science." in tex
    assert rendered["released"] is False
    assert rendered["project_state"] != "RELEASED"
    if find_engine() is not None:
        assert rendered["status"] == "rendered"
        assert (root / "latex" / "draft.pdf").read_bytes().startswith(b"%PDF-")
    else:
        assert rendered["status"] == "compiler_missing"
        assert not (root / "latex" / "draft.pdf").exists()


def test_tikz_without_an_output_stays_unchecked(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _topic(tmp_path)
    excerpt_id = _ready(session)
    recorded = dispatch(
        "studium_figure_record",
        {
            "section": "tema-1",
            "caption": "A line from the opened page.",
            "kind": "tikz",
            "source": r"\draw (0,0) -- (1,1);",
            "excerpts": [excerpt_id],
        },
        session=session,
    )
    assert recorded["status"] == "recorded"
    checked = dispatch("studium_figure_check", {"id": recorded["figure"]["id"]}, session=session)
    pdf = root / "figures" / recorded["figure"]["id"] / "figure.pdf"
    if pdf.is_file() and checked["checked"] is True:
        assert checked["status"] == "checked"
        assert checked["figure"]["proves_science"] is False
    else:
        assert checked["checked"] is False
        assert checked["status"] == "unchecked"
        assert checked["figure"]["correct"] is False
        assert not pdf.exists()
    assert checked["released"] is False
    assert "verified" not in json.dumps(checked)
    fetched = dispatch(
        "studium_figure_record",
        {
            "section": "tema-1",
            "caption": "Do not fetch.",
            "kind": "python",
            "source": "import urllib.request\nurllib.request.urlopen('https://example.com')\n",
            "excerpts": [excerpt_id],
        },
        session=session,
    )
    assert fetched["status"] == "figure.source_forbidden"
    assert fetched["checked"] is False


def _topic(tmp_path):
    session = open_workspace(str(tmp_path))
    assert (
        dispatch(
            "studium_project_create",
            {"slug": "historia", "topic": "Historia medieval"},
            session=session,
        )["status"]
        == "created"
    )
    return session, tmp_path / "historia"


def _ready(session) -> str:
    source = dispatch(
        "studium_public_source_record",
        {"title": "Open page", "url": "https://open.example/historia"},
        session=session,
    )
    assert source["status"] == "recorded"
    source_id = str(source["candidate"]["id"])
    excerpt = dispatch(
        "studium_excerpt_record",
        {
            "source_id": source_id,
            "url": "https://open.example/historia",
            "text": "A stored excerpt is data, not a source of authority.",
        },
        session=session,
    )
    assert excerpt["status"] == "recorded"
    dispatch(
        "studium_blueprint_store",
        {"sections": [{"id": "tema-1", "title": "Origenes"}]},
        session=session,
    )
    return str(excerpt["excerpt"]["id"])


def _explode(*_args, **_kwargs):
    raise AssertionError("must not fetch")
