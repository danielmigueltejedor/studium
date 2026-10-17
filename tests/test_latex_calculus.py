"""Derivatives, integrals and matrices in LaTeX relations: read exactly, or refused."""

import pytest
from test_grounding import _book, _excerpt, _explode

from studium.authoring.grounding import equation_evidence
from studium.authoring.latex_calculus import as_definition, check_relation
from studium.mcp.server import dispatch


def _kind(statement, defs=None):
    outcome = check_relation(statement, defs or {})
    return None if outcome is None else outcome.kind


@pytest.mark.parametrize(
    "statement",
    [
        r"\frac{d}{dx}\left(\frac{q x^{4}}{24 E I}\right) = \frac{q x^{3}}{6 E I}",
        r"\frac{d^{2}}{dx^{2}}\left(x^{4}\right) = 12 x^{2}",
        r"\int_0^L x(L-x)\,dx = \frac{L^{3}}{6}",
        r"\int_0^{R} U_{\max}\left(1 - \frac{r^{2}}{R^{2}}\right) 2\pi r\,dr = \frac{\pi R^{2} U_{\max}}{2}",
        r"\sin^2\theta + \cos^2\theta = 1",
        r"\frac12 + \frac13 = \frac56",
        r"\sin(30^\circ) = \frac12",
        r"\log_{10}(1000) = 3",
        r"\begin{bmatrix} k & -k \\ -k & k \end{bmatrix}\begin{bmatrix} 1 \\ 1 \end{bmatrix} = \begin{bmatrix} 0 \\ 0 \end{bmatrix}",
        r"\begin{bmatrix} 2 & 1 \\ 1 & 2 \end{bmatrix}^{-1} = \frac13\begin{bmatrix} 2 & -1 \\ -1 & 2 \end{bmatrix}",
        r"\begin{bmatrix} 1 & 2 \\ 3 & 4 \end{bmatrix}^{\mathsf{T}} = \begin{bmatrix} 1 & 3 \\ 2 & 4 \end{bmatrix}",
    ],
)
def test_explicit_identities_are_verified(statement):
    assert _kind(statement) == "identity"


@pytest.mark.parametrize(
    "statement",
    [
        r"\begin{bmatrix} k & -k \\ -k & k \end{bmatrix}\begin{bmatrix} 1 \\ 0 \end{bmatrix} = \begin{bmatrix} 0 \\ 0 \end{bmatrix}",
        r"\mathbf{F} = m\mathbf{a}",
        r"\Delta p = \rho g \Delta h",
    ],
)
def test_a_relation_that_is_not_an_identity_is_unknown_never_verified(statement):
    assert _kind(statement) == "unknown"


def test_constant_differences_between_exact_sides_are_contradictions_but_decimals_are_not():
    assert _kind(r"\int_0^1 x\,dx = \frac13") == "contradiction"
    assert _kind(r"\frac12 + \frac13 = \frac45") == "contradiction"
    # A decimal literal may be a rounded value of an irrational: never a contradiction.
    assert _kind(r"\sqrt{2\cdot 9{,}81\cdot 1000} = 140") == "unknown"
    assert _kind(r"\int_0^1 x\,dx = 0.33") == "unknown"


@pytest.mark.parametrize(
    "statement",
    [
        r"\frac{d(m v)}{dt} = m\frac{dv}{dt}",  # nothing says m or v depend on t
        r"\mathbf{F}\cdot\mathbf{v} = P",
        r"\mathbf{L}_O = \mathbf{r}\times m\mathbf{v}",
        r"\nabla\cdot\mathbf{u} = 0",
        r"\oint_C \mathbf{F}\cdot d\mathbf{r} = 0",
        r"\int f\,dx = F",
        r"M = \sum_i m_i",
        r"\frac{d}{dt} = 1",
    ],
)
def test_notation_that_cannot_be_read_faithfully_is_refused(statement):
    assert check_relation(statement, {}) is None


def test_a_derivative_is_never_read_as_a_product():
    assert _kind(r"\tau = \mu\,\frac{du}{dy}") == "unknown"
    # u is discovered as a function of y: du/dy and u/y are different things.
    assert _kind(r"\frac{du}{dy} = \frac{u}{y}") == "unknown"
    assert _kind(r"\frac{dm}{dt} = \dot m") == "identity"


def test_definitions_stated_earlier_are_premises_a_relation_may_follow_from():
    definition = as_definition(r"w(x) = \frac{q x^{4}}{24 E I}", {})
    assert definition is not None and definition.name == "w" and definition.variables == ("x",)
    defs = {definition.name: definition}
    for statement in (
        r"\frac{dw}{dx} = \frac{q x^{3}}{6 E I}",
        r"w'(x) = \frac{q x^{3}}{6 E I}",
        r"\frac{d^{4} w}{dx^{4}} = \frac{q}{E I}",
        r"E I\,w^{\prime\prime\prime\prime}(x) = q",
        r"w''(L) = \frac{q L^{2}}{2 E I}",
    ):
        outcome = check_relation(statement, defs)
        assert outcome is not None and outcome.kind == "identity", statement
        assert outcome.premises == (definition.statement,)
    wrong = check_relation(r"w'(x) = \frac{q x^{3}}{7 E I}", defs)
    assert wrong is not None and wrong.kind == "unknown"
    # Without the definition nothing follows.
    assert _kind(r"w'(x) = \frac{q x^{3}}{6 E I}") is None or _kind(r"w'(x) = \frac{q x^{3}}{6 E I}") == "unknown"


def test_matrix_definitions_chain_into_a_stiffness_check():
    stiffness = as_definition(r"\mathbf{K} = \frac{E A}{L}\begin{bmatrix} 1 & -1 \\ -1 & 1 \end{bmatrix}", {})
    assert stiffness is not None
    defs = {stiffness.name: stiffness}
    displacement = as_definition(r"\mathbf{u} = \begin{bmatrix} 0 \\ \delta \end{bmatrix}", defs)
    assert displacement is not None
    defs[displacement.name] = displacement
    good = check_relation(r"\mathbf{K}\mathbf{u} = \frac{E A \delta}{L}\begin{bmatrix} -1 \\ 1 \end{bmatrix}", defs)
    assert good is not None and good.kind == "identity" and len(good.premises) == 2
    bad = check_relation(r"\mathbf{K}\mathbf{u} = \frac{E A \delta}{L}\begin{bmatrix} 1 \\ 1 \end{bmatrix}", defs)
    assert bad is not None and bad.kind == "unknown"


def test_a_definition_must_be_explicit_and_not_circular():
    assert as_definition(r"x = 0", {}) is None  # a value or condition holds at one place
    assert as_definition(r"a = a + 1", {}) is None
    assert as_definition(r"\frac{dw}{dx} = \theta", {}) is None
    assert as_definition(r"w(x) = \frac{d u}{d x}", {}) is None


def _paragraph(session, text, excerpts):
    recorded = dispatch("studium_paragraph_record", {"section": "presion", "text": text, "excerpts": excerpts}, session=session)
    assert recorded["status"] == "recorded", recorded
    return recorded["paragraph"]


def test_a_beam_paragraph_is_checked_step_by_step_without_claiming_its_premise(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _book(tmp_path)
    excerpt = _excerpt(session, "La presión es fuerza por unidad de área.")
    paragraph = _paragraph(
        session,
        r"La flecha de la viga empotrada con carga uniforme es $w(x) = \frac{q x^{4}}{24 E I}$, "
        r"su giro $w'(x) = \frac{q x^{3}}{6 E I}$ y la carga $E I\,w^{\prime\prime\prime\prime}(x) = q$; "
        r"un giro mal derivado sería $w'(x) = \frac{q x^{3}}{7 E I}$.",
        [excerpt],
    )
    items = {item["statement"]: item for item in equation_evidence(root, paragraph)}
    flecha = items[r"w(x) = \frac{q x^{4}}{24 E I}"]
    assert flecha["status"] == "unsupported" and flecha["premises"] == []
    giro = items[r"w'(x) = \frac{q x^{3}}{6 E I}"]
    assert giro["status"] == "follows_from_stated_premises"
    assert giro["premises"] == [r"w(x) = \frac{q x^{4}}{24 E I}"] and giro["human_review"] == "required"
    assert items[r"E I\,w^{\prime\prime\prime\prime}(x) = q"]["status"] == "follows_from_stated_premises"
    # A wrong step is not blessed by the premise and is not called false either: it stays for human review.
    wrong = items[r"w'(x) = \frac{q x^{3}}{7 E I}"]
    assert wrong["status"] == "not_machine_checkable" and wrong["human_review"] == "required"
    assert wrong["premises"] == [r"w(x) = \frac{q x^{4}}{24 E I}"]
    summary = dispatch("studium_quality_report", {}, session=session)["math_grounding"]
    assert summary["by_status"]["follows_from_stated_premises"] == 2
    assert summary["scientific_verification_complete"] is False


def test_an_explicit_integral_identity_is_symbolically_verified_and_a_wrong_one_is_contradicted(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _book(tmp_path)
    excerpt = _excerpt(session, "La presión es fuerza por unidad de área.")
    good = _paragraph(session, r"El área bajo la parábola vale $\int_0^L x(L-x)\,dx = \frac{L^{3}}{6}$ en total.", [excerpt])
    (item,) = equation_evidence(root, good)
    assert item["status"] == "symbolically_verified" and item["evidence"] == ["sympy"] and item["human_review"] == "none"
    bad = _paragraph(session, r"Por error se escribe $\int_0^1 x\,dx = \frac13$ para el área.", [excerpt])
    (wrong,) = equation_evidence(root, bad)
    assert wrong["status"] == "contradicted" and wrong["blocks_audit"] is True


def test_conditions_are_never_premises_for_other_relations(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _book(tmp_path)
    excerpt = _excerpt(session, "La presión es fuerza por unidad de área.")
    paragraph = _paragraph(session, r"En el origen $t = 0$ se tiene $x = 0$, y para todo instante $x = u_0 t$ en la trayectoria.", [excerpt])
    statuses = {item["statement"]: item["status"] for item in equation_evidence(root, paragraph)}
    assert statuses["t = 0"] == "value_or_condition" and statuses["x = 0"] == "value_or_condition"
    assert statuses["x = u_0 t"] == "unsupported"


def test_a_computed_integral_or_derivative_that_differs_from_the_stated_closed_form_is_contradicted():
    wrong = check_relation(r"\int_0^L \frac{q^{2}(L-x)^{4}}{8 E I}\,dx = \frac{q^{2} L^{5}}{24 E I}", {})
    assert wrong is not None and wrong.kind == "contradiction" and "sample point" in wrong.detail
    right = check_relation(r"\int_0^L \frac{q^{2}(L-x)^{4}}{8 E I}\,dx = \frac{q^{2} L^{5}}{40 E I}", {})
    assert right is not None and right.kind == "identity"
    derivative = check_relation(r"\frac{d}{dx}\left(\frac{q x^{4}}{24 E I}\right) = \frac{q x^{3}}{5 E I}", {})
    assert derivative is not None and derivative.kind == "contradiction"
    # An equation to solve that involves no computed integral or derivative is never called false.
    assert _kind(r"x^{2} = 4") == "unknown"
    assert _kind(r"\sin\theta = \frac12") == "unknown"


def test_a_definition_is_not_a_claim_that_two_expressions_coincide():
    # U = integral(...) defines U; the free symbols differ, so no verdict on it.
    assert _kind(r"U = \int_0^L \frac{q^{2}(L-x)^{4}}{8 E I}\,dx") == "unknown"
    # A value of an undefined function is opaque: u(0) is never the product of u and 0.
    assert _kind(r"u(0) = 0") == "unknown"
    assert check_relation(r"\int_0^L \frac{M(x)^{2}}{2 E I}\,dx = U", {}) is None


def test_the_first_statement_about_a_name_defines_it(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, root = _book(tmp_path)
    excerpt = _excerpt(session, "La presión es fuerza por unidad de área.")
    paragraph = _paragraph(
        session,
        r"La flecha es $w(x) = \frac{q x^{2}}{24 E I}\left(6L^{2} - 4Lx + x^{2}\right)$, el giro "
        r"$w'(x) = \frac{q x}{6 E I}\left(3L^{2} - 3Lx + x^{2}\right)$, la flecha en el extremo $w(L) = \frac{q L^{4}}{8 E I}$ "
        r"y el giro en el extremo $w'(L) = \frac{q L^{3}}{6 E I}$.",
        [excerpt],
    )
    statuses = [item["status"] for item in equation_evidence(root, paragraph)]
    assert statuses == ["unsupported"] + ["follows_from_stated_premises"] * 3


def test_an_explicit_definition_is_a_premise_for_later_relations_in_the_paragraph(tmp_path):
    from studium.authoring.grounding import equation_evidence

    record = {
        "id": "PAR-0001",
        "section": "x",
        "excerpts": [],
        "text": (
            r"La flecha $w(x) := \frac{q x^{4}}{24 E I}$ tiene por giro $w'(x) = \frac{q x^{3}}{6 E I}$ "
            r"y no vale $w'(x) = \frac{q x^{3}}{7 E I}$."
        ),
    }
    items = {item["statement"]: item for item in equation_evidence(tmp_path, record)}
    giro = items[r"w'(x) = \frac{q x^{3}}{6 E I}"]
    assert giro["status"] == "follows_from_stated_premises" and giro["human_review"] == "required"
    assert items[r"w'(x) = \frac{q x^{3}}{7 E I}"]["status"] not in {"follows_from_stated_premises", "symbolically_verified"}


def test_a_greek_letter_can_be_the_variable_of_integration():
    right = check_relation(r"\int_{0}^{2\pi} \left(R\sin\theta\right)^{2}\,t\,R\,\mathrm{d}\theta = \pi R^{3}\,t", {})
    assert right is not None and right.kind == "identity"
    wrong = check_relation(r"\int_{0}^{2\pi} \left(R\sin\theta\right)^{2}\,t\,R\,\mathrm{d}\theta = \pi R^{3}\,t^{2}", {})
    assert wrong is not None and wrong.kind == "contradiction"
    assert check_relation(r"\int_0^{\pi} \cos\theta\,\mathrm{d}\theta = 1", {}).kind == "contradiction"


def test_thin_space_ends_an_unparenthesised_function_argument():
    """Regression (Theory of Structures book): ``\\sin x\\,R`` was read as sin(x R)."""

    import sympy

    from studium.authoring.latex_calculus import _Context, _parse_side

    x, r = sympy.symbols("x R")
    assert sympy.simplify(_parse_side(r"\sin x\,R", _Context()) - sympy.sin(x) * r) == 0
    assert sympy.simplify(_parse_side(r"\sin x R", _Context()) - sympy.sin(x * r)) == 0


@pytest.mark.parametrize("quotient", ["dh/dT", "dh / dT", "dh/(dT)", "d^2h/dT^2", r"dh/\mathrm{d}T"])
def test_inline_differential_quotients_never_become_algebraic_premises(quotient):
    assert check_relation("c_p=" + quotient) is None
    assert as_definition("c_p=" + quotient, {}) is None


@pytest.mark.parametrize("argument", ["T", "T_r", r"\vartheta", "0", "-1"])
def test_opaque_function_values_keep_their_arguments(argument):
    assert _kind(f"h({argument})=h*({argument})") == "unknown"
    scalar = as_definition(r"h=e+p/\rho", {})
    assert scalar is not None
    # A scalar definition does not establish a temperature-dependent function.
    assert check_relation(f"h({argument})=h*({argument})", {scalar.name: scalar}) is None


@pytest.mark.parametrize("variable", ["x", r"\vartheta"])
def test_an_integrand_with_unknown_functional_dependence_is_not_a_product(variable):
    statement = rf"\int_0^T c_p({variable})\,d{variable}=c_p*T^2/2"
    assert check_relation(statement) is None
    constant = as_definition(r"c_p=\gamma R/(\gamma-1)", {})
    assert constant is not None
    assert check_relation(statement, {constant.name: constant}) is None


def test_variable_heat_capacity_paragraph_does_not_create_a_false_contradiction(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", _explode)
    session, _root = _book(tmp_path)
    excerpt = _excerpt(session, "Contexto sintético de una relación termodinámica.")
    paragraph = _paragraph(
        session,
        r"La entalpía específica es \(h=e+p/\rho\). Para el modelo térmico "
        r"\(e=e(T)\) y \(h=h(T)\). Se escriben \(c_v=de/dT\), \(c_p=dh/dT\) "
        r"y \(c_p-c_v=R\). Sólo si los calores específicos son constantes, "
        r"\(h(T)-h(T_r)=c_p(T-T_r)\), \(c_p=\gamma R/(\gamma-1)\) "
        r"y \(\gamma=c_p/c_v\). Con capacidad calorífica variable se usa "
        r"\[h(T)-h(T_r)=\int_{T_r}^{T}c_p(\vartheta)\,d\vartheta\].",
        [excerpt],
    )
    report = dispatch("studium_equation_report", {}, session=session)
    integral = next(item for item in report["equations"] if r"\int" in item["statement"])
    assert integral["paragraph"] == paragraph["id"]
    assert integral["status"] == "not_machine_checkable"
    assert integral["human_review"] == "required"
    assert integral["evidence"] == []
    assert not any(item["status"] == "contradicted" for item in report["equations"])


def test_explicit_function_definitions_still_allow_integral_checks():
    definition = as_definition("c_p(x)=a+b*x", {})
    assert definition is not None
    good = check_relation(r"\int_0^T c_p(x)\,dx=a*T+b*T^2/2", {definition.name: definition})
    bad = check_relation(r"\int_0^T c_p(x)\,dx=a*T+b*T^2/3", {definition.name: definition})
    assert good is not None and good.kind == "identity"
    assert bad is not None and bad.kind == "contradiction"


def test_scalar_products_can_still_be_written_unambiguously():
    definition = as_definition("a=b+c", {})
    assert definition is not None
    defs = {definition.name: definition}
    assert _kind(r"a\cdot(x)=(b+c)*x", defs) == "identity"
    assert _kind(r"a(x+1)=(b+c)*(x+1)", defs) == "identity"
    assert _kind(r"\int_0^T c_p*x\,dx=c_p*T^2/2") == "identity"
