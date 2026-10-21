"""Preserve a usable edition when a later build fails or overlaps another."""

import json
import threading

import pytest

from studium.authoring import render


@pytest.fixture
def render_project(tmp_path, monkeypatch):
    (tmp_path / '.studium').mkdir()
    (tmp_path / 'latex').mkdir()
    monkeypatch.setattr(render, 'load_state_holding_lock', lambda _: {'state': 'DRAFT'})
    monkeypatch.setattr(render, 'book_language', lambda _: object())
    monkeypatch.setattr(render, '_document', lambda *args, **kwargs: 'new source')
    monkeypatch.setattr(render, '_first_unwritten_title', lambda *args, **kwargs: None)
    monkeypatch.setattr(render, 'supported_drafts', lambda _: [])
    monkeypatch.setattr(render, 'supported_paragraphs', lambda _: [])
    return tmp_path


def _previous(root):
    tex = root / 'latex/draft.tex'
    pdf = root / 'latex/draft.pdf'
    tex.write_text('previous source')
    pdf.write_bytes(b'%PDF-1.4\nprevious edition')
    return tex, pdf


@pytest.mark.parametrize('compiler_available', [False, True])
def test_failed_attempt_preserves_previous_source_and_pdf(render_project, monkeypatch, compiler_available):
    root = render_project
    tex, pdf = _previous(root)
    before = (tex.read_bytes(), pdf.read_bytes())
    monkeypatch.setattr(render, 'find_engine', lambda: 'pdflatex' if compiler_available else None)

    def compile_failure(_engine, staged, _out):
        staged.with_suffix('.pdf').write_bytes(b'%PDF-1.4\nincomplete output')
        staged.with_suffix('.log').write_text('! Undefined control sequence.\nl.1 bad')
        return False, 'test failure'

    monkeypatch.setattr(render, '_compile', compile_failure)
    result = render.render_draft(root)
    assert result['status'] == ('render.compile_failed' if compiler_available else 'compiler_missing')
    assert result['pdf'] is None
    assert result['previous_pdf'] == 'latex/draft.pdf'
    assert (tex.read_bytes(), pdf.read_bytes()) == before
    assert (root / result['tex']).read_text() == 'new source'
    report = json.loads((root / result['editorial_report']).read_text())
    assert report['compiled'] is False
    assert not list(root.glob('.studium-render-*'))


def test_second_render_cannot_enter_compiler(render_project, monkeypatch):
    root = render_project
    entered = threading.Event()
    release = threading.Event()
    outcomes = []
    calls = []
    monkeypatch.setattr(render, 'find_engine', lambda: 'pdflatex')

    def compile_blocked(_engine, staged, _out):
        calls.append(staged)
        entered.set()
        assert release.wait(10)
        return False, 'test compiler failure'

    monkeypatch.setattr(render, '_compile', compile_blocked)
    thread = threading.Thread(target=lambda: outcomes.append(render.render_draft(root)))
    thread.start()
    try:
        assert entered.wait(10)
        assert render.render_draft(root)['status'] == 'storage.locked'
        assert len(calls) == 1
    finally:
        release.set()
        thread.join(10)
    assert not thread.is_alive()
    assert outcomes[0]['status'] == 'render.compile_failed'
    assert not (root / '.studium/write.lock').exists()


def test_success_retains_recoverable_previous_pair(render_project, monkeypatch):
    root = render_project
    tex, pdf = _previous(root)
    before = (tex.read_bytes(), pdf.read_bytes())
    monkeypatch.setattr(render, 'find_engine', lambda: 'pdflatex')

    def compile_success(_engine, staged, _out):
        assert tex.read_bytes() == before[0] and pdf.read_bytes() == before[1]
        staged.with_suffix('.pdf').write_bytes(b'%PDF-1.4\nnew edition')
        return True, ''

    monkeypatch.setattr(render, '_compile', compile_success)
    result = render.render_draft(root)
    assert result['status'] == 'rendered'
    assert tex.read_text() == 'new source'
    assert pdf.read_bytes() == b'%PDF-1.4\nnew edition'
    backup = root / result['previous_artifacts']
    assert (backup / 'draft.tex').read_bytes() == before[0]
    assert (backup / 'draft.pdf').read_bytes() == before[1]


def test_compiler_exception_does_not_replace_last_good_pair(render_project, monkeypatch):
    root = render_project
    tex, pdf = _previous(root)
    before = (tex.read_bytes(), pdf.read_bytes())
    monkeypatch.setattr(render, 'find_engine', lambda: 'pdflatex')

    def interrupted(*_args):
        raise OSError('interrupted compiler IO')

    monkeypatch.setattr(render, '_compile', interrupted)
    assert render.render_draft(root)['status'] == 'render.write_failed'
    assert (tex.read_bytes(), pdf.read_bytes()) == before
    assert not (root / '.studium/write.lock').exists()


def test_backup_cannot_escape_project(render_project, monkeypatch, tmp_path_factory):
    root = render_project
    tex, pdf = _previous(root)
    before = (tex.read_bytes(), pdf.read_bytes())
    outside = tmp_path_factory.mktemp('outside-render-project')
    (root / '.studium/render-backups').symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(render, 'find_engine', lambda: 'pdflatex')

    def compile_success(_engine, staged, _out):
        staged.with_suffix('.pdf').write_bytes(b'%PDF-1.4\nnew edition')
        return True, ''

    monkeypatch.setattr(render, '_compile', compile_success)
    assert render.render_draft(root)['status'] == 'render.write_failed'
    assert (tex.read_bytes(), pdf.read_bytes()) == before
    assert list(outside.iterdir()) == []


def test_symlinked_previous_pdf_is_rejected(render_project):
    root = render_project
    previous = root / 'original.pdf'
    previous.write_bytes(b'%PDF-1.4\nprevious edition')
    (root / 'latex/draft.pdf').symlink_to(previous)
    assert render.render_draft(root)['status'] == 'render.path_escaped'
    assert previous.read_bytes() == b'%PDF-1.4\nprevious edition'

