"""A stored production flag does not replace a present figure artifact."""

import pytest

from studium.authoring import completeness, render
from studium.authoring.figure_artifacts import checked_figure_output


def test_missing_figure_cannot_satisfy_completeness(tmp_path, monkeypatch):
    figure = {
        'id': 'FIG-0001', 'section': 'test', 'status': 'checked', 'correct': True,
        'output': 'figures/FIG-0001/figure.png',
    }
    for name, value in (
        ('derivations_for_section', []), ('_sources_for_section', set()),
        ('academic_concepts_for_chapter', []), ('academic_sections_for_chapter', []),
        ('_notation_count', 0), ('planned_figures_for_chapter', 1),
    ):
        monkeypatch.setattr(completeness, name, lambda *_args, value=value: value)
    context = {
        'profile': 'STEM', 'paragraphs': [], 'problems': [], 'figures': [figure],
        'audited': set(), 'contradictions': set(), 'source_count': 0,
    }

    def check():
        report = completeness._section_report(tmp_path, 'test', context)
        return next(item for item in report['checks'] if item['id'] == 'figures_checked')['met']

    assert check() is False
    output = tmp_path / str(figure['output'])
    output.parent.mkdir(parents=True)
    output.write_bytes(b'nonempty existing artifact')
    assert check() is True
    figure['correct'] = False
    assert check() is False
    figure['correct'] = True
    output.unlink()
    assert check() is False
    assert render._checked_output(tmp_path, figure) is None


@pytest.mark.parametrize('output', ['../figure.png', 'figures/FIG-0001/other.png', '/figure.pdf', None])
def test_invalid_figure_output_is_unavailable(tmp_path, output):
    assert checked_figure_output(tmp_path, {'status': 'checked', 'correct': True, 'output': output}) is None


def test_symlinked_figure_output_is_unavailable(tmp_path):
    output = tmp_path / 'figures/FIG-0001/figure.png'
    output.parent.mkdir(parents=True)
    original = tmp_path / 'original.png'
    original.write_bytes(b'figure')
    output.symlink_to(original)
    assert checked_figure_output(tmp_path, {
        'status': 'checked', 'correct': True, 'output': 'figures/FIG-0001/figure.png',
    }) is None


def test_missing_figure_is_reported_in_reference_and_usage_views(tmp_path, monkeypatch):
    from studium.authoring.figures import figure_usage, unresolved_figure_references
    from studium.storage.records import FIGURES, append_jsonl

    figure = {
        'id': 'FIG-0001', 'section': 'test', 'key': 'control-volume',
        'status': 'checked', 'correct': True, 'output': 'figures/FIG-0001/figure.png',
    }
    append_jsonl(tmp_path / FIGURES, figure)
    monkeypatch.setattr(
        'studium.authoring.paragraphs.supported_paragraphs',
        lambda _: [{'id': 'PAR-0001', 'text': 'See {{fig:control-volume}}.'}],
    )
    assert unresolved_figure_references(tmp_path) == [
        {'paragraph': 'PAR-0001', 'key': 'control-volume', 'reason': 'unchecked'},
    ]
    assert figure_usage(tmp_path)[0]['checked'] is False
    output = tmp_path / 'figures/FIG-0001/figure.png'
    output.parent.mkdir(parents=True)
    output.write_bytes(b'figure')
    assert unresolved_figure_references(tmp_path) == []
    assert figure_usage(tmp_path)[0]['checked'] is True


def test_reference_to_an_undrawn_figure_is_not_numbered(tmp_path):
    from studium.authoring import render

    token = render._DRAWN_FIGURE_KEYS.set(frozenset({'dibujada'}))
    try:
        drawn = render._render_figure_refs('Ver {{fig:dibujada}}.', 'figura')
        missing = render._render_figure_refs('Ver {{fig:sin-archivo}}.', 'figura')
    finally:
        render._DRAWN_FIGURE_KEYS.reset(token)
    assert '\\ref{fig:dibujada}' in drawn
    assert '\\ref' not in missing
    assert 'sin-archivo' in missing
