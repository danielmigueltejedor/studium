"""A learner can compare the reasoning and every intermediate calculation."""
from studium.authoring.languages import describe, messages
from studium.authoring.render import _solution_body, _steps_lines


def test_reasoning_survives_without_any_diagram():
    language = describe('es')
    assert language is not None
    solution = {
        'development': ['La fuerza neta constante permite usar $F=ma$.',
                        'Integrar $dv/dt=a$ con $v(0)=0$ da $v=at$.'],
        'steps': [{'text': 'Despejar la aceleración antes del tiempo.',
                   'equation': 'a=F/m', 'expression': '150000/70000',
                   'expected': '2.142857', 'unit': 'm/s^2'},
                  {'text': 'El tiempo corresponde a alcanzar 75 m/s.',
                   'expression': '75/(150000/70000)', 'unit': 's'}],
    }
    rendered = '\n'.join(_solution_body({'id': 'PRB-0001'}, solution, messages(language), language))
    assert 'permite usar' in rendered and 'Integrar' in rendered
    assert rendered.index('Integrar') < rendered.index('Despejar')
    assert r'\approx 2.1428571' in rendered
    assert '= 35' in rendered
    assert r'\mathrm{s}' in rendered


def test_printed_intermediate_is_calculated_not_copied_from_expected():
    language = describe('es')
    assert language is not None
    rendered = '\n'.join(_steps_lines([
        {'text': 'Suma', 'expression': '2+3', 'expected': '999'},
        {'text': 'Legado inválido', 'expression': 'bad(payload)'},
    ], language))
    assert '= 5' in rendered and '999' not in rendered
    assert 'bad(payload)' in rendered
