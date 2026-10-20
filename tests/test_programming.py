"""Programming checks measure the property named in their result."""

import shutil

import pytest

from studium.authoring.audit import _asserted_quantities
from studium.authoring.grounding import math_statements
from studium.authoring.literals import code_regions, mask_code
from studium.authoring.programming import ExerciseContract, listing_findings
from studium.authoring.render import _escape_delimiters, emit_prose, render_text_run
from studium.verification.programs import CodeArtifact, verify_program


def test_code_never_supplies_equations_to_scientific_grounding():
    text = '```python\nx = 2 + 3\nprint("$E = m*c^2$")\n```\nLa fórmula es $F = m*a$.'
    statements = math_statements(text)
    assert statements == [("claim", "F = m*a")]
    assert _asserted_quantities('```rust\nlet n = 42;\n```') == []
    assert len(mask_code(text)) == len(text)


def test_long_fences_inline_ticks_and_unclosed_fences_are_opaque():
    text = '````python\nx = 1\n```\ny = 2\n`````\nUsa ``a`b_c``.\n~~~sql\nx = 8 + 9'
    regions = code_regions(text)
    assert len(regions) == 3
    assert '```' in regions[0].body
    assert regions[1].body == 'a`b_c'
    assert not regions[-1].closed
    assert math_statements(text) == []
    assert listing_findings(text)[0]['type'] == 'unclosed_code_fence'
    assert r'\texttt{a`b\_c}' in render_text_run('Usa ``a`b_c``.')


def test_escape_delimiters_cannot_collide_with_source():
    source = '(*@ @*) (#@ @#) (|@ @|) [<@ @>] (*studium0@ @studium0*)'
    begin, end = _escape_delimiters(source)
    assert begin not in source and end not in source


def test_programming_contracts_do_not_require_units_or_physical_models():
    assert ExerciseContract('implementation', 'Implement a parser.', 'Solution', ('empty input',)).gaps() == []
    assert ExerciseContract('architecture', 'Compare consistency models.', 'Tradeoffs', rubric=('state assumptions',)).gaps() == []
    assert ExerciseContract('debugging', 'Fix this program.', 'Solution').gaps() == ['tests']


def test_syntax_is_not_behavior_and_untrusted_code_is_not_run(tmp_path):
    payload = f'open({str(tmp_path / "should-not-exist")!r}, "w").write("ran")'
    parsed = verify_program(CodeArtifact('python', payload))
    assert parsed['classification'] == 'SYNTAX_VALIDATED'
    refused = verify_program(CodeArtifact('python', payload, mode='run'))
    assert refused['classification'] == 'ISOLATION_REQUIRED'
    assert not (tmp_path / 'should-not-exist').exists()
    assert verify_program(CodeArtifact('python', 'not valid code'))['classification'] == 'FAILED'
    assert verify_program(CodeArtifact('json', '{"bad": NaN}'))['classification'] == 'FAILED'
    assert verify_program(CodeArtifact('html', '<>'))['classification'] == 'UNVERIFIED'


def test_expected_stdout_is_checked_exactly_and_empty_tests_do_not_pass():
    artifact = CodeArtifact('python', 'print("hello")', mode='run', expected_stdout='hello\n')
    result = verify_program(artifact, trusted=True)
    assert result['classification'] == 'OUTPUT_MATCHED', result
    assert result['source_sha256'] == artifact.sha256
    assert result['tool_version']
    assert verify_program(CodeArtifact('python', 'print("wrong")', mode='run', expected_stdout='right\n'), trusted=True)['classification'] == 'FAILED'
    assert verify_program(CodeArtifact('python', 'pass', mode='run'), trusted=True)['classification'] == 'EXECUTED'
    assert verify_program(CodeArtifact('python', 'pass', mode='test'), trusted=True)['classification'] == 'UNVERIFIED'
    tests = 'import unittest\nclass Tests(unittest.TestCase):\n    def test_ok(self):\n        self.assertEqual(2 + 2, 4)\n'
    assert verify_program(CodeArtifact('python', tests, mode='test'), trusted=True)['classification'] == 'TESTS_PASSED'


def test_timeout_and_missing_tool_are_explicit(monkeypatch):
    result = verify_program(CodeArtifact('python', 'while True: pass', mode='run'), trusted=True, timeout=.1)
    assert result['classification'] == 'TIMEOUT'
    monkeypatch.setattr(shutil, 'which', lambda _: None)
    assert verify_program(CodeArtifact('rust', 'fn main() {}', mode='run'), trusted=True)['classification'] == 'PENDING_TOOLCHAIN'


def test_terminal_output_and_diagnostic_have_distinct_styles():
    terminal = '\n'.join(emit_prose('```terminal\npython app.py\n```'))
    output = '\n'.join(emit_prose('```output\n42\n```'))
    error = '\n'.join(emit_prose('```error\nSyntaxError: invalid syntax\n```'))
    assert 'title={Terminal}' in terminal and 'backgroundcolor=' in terminal
    assert 'title={Output}' in output
    assert 'title={Diagnostic}' in error and 'rulecolor=' in error


@pytest.mark.skipif(shutil.which('rustc') is None, reason='rustc unavailable')
def test_rust_tests_are_counted_and_empty_suites_do_not_pass():
    good = '#[test]\nfn test_add() { assert_eq!(2+2, 4); }'
    assert verify_program(CodeArtifact('rust', good, mode='test'), trusted=True)['classification'] == 'TESTS_PASSED'
    assert verify_program(CodeArtifact('rust', '', mode='test'), trusted=True)['classification'] == 'UNVERIFIED'


def test_prose_results_paragraphs_and_percent_units_preserve_semantics():
    from studium.authoring.render import _result_lines, _unit_tex
    text = 'Resultado = 96. La estructura ocupa 96 bytes en esta plataforma.'
    rendered = '\n'.join(_result_lines(text))
    assert 'La estructura ocupa' in rendered
    assert r'\[' not in rendered
    assert '\n\n' in '\n'.join(emit_prose('First paragraph.\n\nSecond paragraph.'))
    assert r'\%' in _unit_tex('%')
    assert r'\textbf{Important}' in render_text_run('**Important** and `**literal**`.')
    assert r'\texttt{**literal**}' in render_text_run('**Important** and `**literal**`.')


def test_editorial_hook_and_unsupported_review_copy_are_explicit(tmp_path, monkeypatch):
    from test_professional_math import _setup

    from studium.authoring.render import _document, _first_unwritten_title
    from studium.storage.records import PARAGRAPHS, append_jsonl
    _, root, _ = _setup(tmp_path, monkeypatch)
    append_jsonl(root / PARAGRAPHS, {'id': 'PAR-review', 'section': 'hidrostatica', 'status': 'draft',
                                   'text': 'Uncorroborated manuscript retained for review.', 'excerpts': ['missing']})
    assert 'Uncorroborated manuscript' not in _document(root)
    assert _first_unwritten_title(root) is not None
    reviewed = _document(root, include_unsupported=True)
    assert 'Uncorroborated manuscript' in reviewed and 'REVISIÓN DE FUENTES PENDIENTE' in reviewed
    assert _first_unwritten_title(root, include_unsupported=True) is None
    (root / 'editorial-config.tex').write_text(r'\def\studiumcustomtitle{Editorial title}')
    assert r'\input{../editorial-config.tex}' in _document(root)


@pytest.mark.skipif(shutil.which('tsc') is None, reason='tsc unavailable')
def test_typescript_uses_typechecker_instead_of_node_javascript_syntax_check():
    artifact = CodeArtifact('typescript', 'declare const brand: unique symbol;\ntype Id = string & { [brand]: true };')
    result = verify_program(artifact, trusted=True)
    assert result['classification'] == 'SYNTAX_VALIDATED', result
    assert verify_program(CodeArtifact('typescript', 'const x: number = "wrong";'), trusted=True)['classification'] == 'FAILED'


def test_figure_cited_only_in_purpose_is_retained_and_marked_in_review_copy(tmp_path, monkeypatch):
    from test_professional_math import _setup

    from studium.authoring.render import _document
    from studium.storage.records import FIGURES, PARAGRAPHS, append_jsonl
    _, root, _ = _setup(tmp_path, monkeypatch)
    append_jsonl(root / PARAGRAPHS, {'id': 'PAR-purpose', 'section': 'hidrostatica', 'status': 'draft', 'role': 'purpose',
                                   'text': 'See {{fig:model}} for this model.', 'excerpts': ['missing']})
    append_jsonl(root / FIGURES, {'id': 'FIG-1', 'key': 'model', 'section': 'hidrostatica', 'kind': 'tikz',
                                'source': r'\draw (0,0) -- (1,1);', 'caption': 'Original model', 'status': 'unchecked'})
    text = _document(root, include_unsupported=True)
    assert text.count(r'\label{fig:model}') == 1
    assert 'DRAFT FIGURE: evidence review pending' in text
    assert r'\label{fig:model}' not in _document(root)


def test_plain_dunder_identifiers_are_not_math_subscripts():
    rendered = render_text_run("La instancia usa __dict__ y __slots__.")
    assert r"\(\_" not in rendered
    assert r"\_\_dict\_\_" in rendered
    assert r"\_\_slots\_\_" in rendered


def test_review_copy_retains_stored_answers_without_promoting_them(tmp_path, monkeypatch):
    from test_professional_math import _setup

    from studium.authoring.render import _document
    from studium.storage.records import PARAGRAPHS, PROBLEMS, append_jsonl
    _, root, _ = _setup(tmp_path, monkeypatch)
    append_jsonl(root / PARAGRAPHS, {'id': 'PAR-1', 'section': 'hidrostatica', 'status': 'draft', 'text': 'Original chapter.', 'excerpts': ['missing']})
    append_jsonl(root / PROBLEMS, {'id': 'PRB-1', 'section': 'hidrostatica', 'role': 'practice', 'kind': 'numeric',
                                  'status': 'unchecked', 'correct': False, 'prompt': 'Original pending exercise.', 'expected': '42'})
    review = _document(root, include_unsupported=True)
    assert 'Respuesta propuesta, sin comprobar' in review
    assert 'Solución propuesta; verificación pendiente.' in review
    assert 'Respuesta propuesta, sin comprobar' not in _document(root)


def test_reader_section_selection_preserves_defaults_and_review_warning(tmp_path, monkeypatch):
    from test_professional_math import _setup

    from studium.authoring.render import _document
    _, root, _ = _setup(tmp_path, monkeypatch)
    original = _document(root)
    assert r"\chapter{Hoja de fórmulas}" in original
    config = root / "project.toml"
    config.write_text(config.read_text() + '\n[render]\nfrontmatter = []\nappendices = ["solutions"]\n')
    before = {p: p.read_bytes() for p in root.rglob("*.jsonl")}
    text = _document(root, include_unsupported=True)
    assert r"\chapter{Soluciones}" in text
    assert r"\begin{thebibliography}" in text
    for title in ("Hoja de fórmulas", "Notación", "Auditoría de fuentes", "Plan de estudio", "Prefacio", "Cómo usar este libro"):
        assert r"\chapter{" + title + "}" not in text
    assert "REVISIÓN DE FUENTES PENDIENTE" in text
    assert {p: p.read_bytes() for p in root.rglob("*.jsonl")} == before


@pytest.mark.parametrize("setting", ['appendices = ["solutions", "solutions"]', 'appendices = ["typo"]', 'frontmatter = "preface"'])
def test_invalid_reader_section_selection_fails_explicitly(tmp_path, monkeypatch, setting):
    from test_professional_math import _setup

    from studium.authoring.render import _document
    _, root, _ = _setup(tmp_path, monkeypatch)
    config = root / "project.toml"
    config.write_text(config.read_text() + "\n[render]\n" + setting + "\n")
    with pytest.raises(ValueError, match="render\\."):
        _document(root)
