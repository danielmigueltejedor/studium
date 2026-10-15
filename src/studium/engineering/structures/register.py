"""Register the structural-mechanics families and generators."""

from studium.diagrams.evidence import Evidence
from studium.diagrams.registry import (
    Family,
    Generated,
    Generator,
    Options,
    register_conventions,
    register_family,
    register_generator,
)
from studium.diagrams.tikz import verify_representation
from studium.engineering.structures import beam_draw
from studium.engineering.structures.beam import (
    laws_latex,
    parse_beam,
    solution_data,
    solve_beam,
    verify_beam,
    verify_virtual_work,
    virtual_work,
)
from studium.engineering.structures.convention import PRESETS


def _beam_check(spec: dict[str, object], claims: object) -> tuple[dict[str, object], Evidence]:
    solution = solve_beam(parse_beam(spec))
    return solution_data(solution), verify_beam(solution, claims)


def _style(options: Options, settings: dict[str, object]) -> beam_draw.Style:
    decimals = settings.get("decimals", options.decimals)
    return beam_draw.Style(comma=options.comma, decimals=int(decimals) if isinstance(decimals, int) else options.decimals)


def _beam_statement(spec, settings, options, claims) -> Generated:
    model = parse_beam(spec)
    solution = solve_beam(model)
    style = _style(options, settings)
    tikz = beam_draw.problem_figure(model, style)
    evidence = verify_beam(solution, claims)
    evidence.extend(beam_draw.verify_geometry(tikz, model, style))
    return Generated(tikz, solution_data(solution), evidence)


def _beam_free_body(spec, settings, options, claims) -> Generated:
    model = parse_beam(spec)
    solution = solve_beam(model)
    style = _style(options, settings)
    with_values = settings.get("values") is True
    tikz = beam_draw.free_body_figure(model, solution if with_values else None, style)
    evidence = verify_beam(solution, claims)
    evidence.extend(beam_draw.verify_geometry(tikz, model, style, free_body=True))
    if with_values:
        evidence.extend(beam_draw.verify_reaction_labels(tikz, solution))
    return Generated(tikz, solution_data(solution), evidence)


def _beam_internal_forces(spec, settings, options, claims) -> Generated:
    model = parse_beam(spec)
    solution = solve_beam(model)
    style = _style(options, settings)
    functions = settings.get("functions")
    chosen = tuple(str(item) for item in functions) if isinstance(functions, list) and functions else ("N", "V", "M")
    tikz, curves, signs = beam_draw.internal_forces_figure(solution, style, chosen)
    evidence = verify_beam(solution, claims)
    evidence.extend(beam_draw.verify_geometry(tikz, model, style, free_body=True))
    evidence.extend(beam_draw.verify_reaction_labels(tikz, solution))
    evidence.extend(verify_representation(tikz, curves, signs))
    return Generated(tikz, solution_data(solution), evidence)


def _beam_deflection(spec, settings, options, claims) -> Generated:
    model = parse_beam(spec)
    solution = solve_beam(model)
    style = _style(options, settings)
    tikz, curves, signs = beam_draw.deflection_figure(solution, style)
    evidence = verify_beam(solution, claims)
    evidence.extend(verify_representation(tikz, curves, signs))
    return Generated(tikz, solution_data(solution), evidence)


def _beam_laws(spec: dict[str, object], options: Options) -> list[str]:
    return laws_latex(solve_beam(parse_beam(spec)), comma=options.comma)


def _beam_virtual_work(spec, settings, options, claims) -> Generated:
    model = parse_beam(spec)
    real = solve_beam(model)
    result = virtual_work(real, settings.get("virtual"))
    style = _style(options, settings)
    tikz, curves, signs = beam_draw.virtual_work_figure(real, result.virtual, style)
    evidence = verify_beam(real, claims if isinstance(claims, dict) and "displacement" not in claims else None)
    evidence.extend(verify_virtual_work(result, claims))
    evidence.extend(verify_representation(tikz, curves, signs))
    data = solution_data(real)
    data["virtual_work"] = {
        "kind": result.kind,
        "at": str(result.at),
        "value": {"exact": str(result.work), "decimal": round(float(result.work), 9) if result.work.is_number else None},
        "elastic_line": str(result.elastic),
        "virtual_M": result.virtual.M.as_dict(),
    }
    return Generated(tikz, data, evidence)


register_family(
    Family(
        "beam",
        "Straight beam: supports (fixed, pin, roller), internal hinges, point forces, couples, "
        "linear distributed loads, optional EI/EA; declared sign convention.",
        _beam_check,
        _beam_laws,
    )
)
register_generator(
    Generator("beam.statement", "beam", "Problem figure: geometry, supports, loads, dimensions, axes.", ("statement",), _beam_statement)
)
register_generator(
    Generator(
        "beam.free_body",
        "beam",
        "Free-body diagram: the beam without supports and its reactions; settings.values prints the solved reactions.",
        ("free_body", "equilibrium"),
        _beam_free_body,
    )
)
register_generator(
    Generator(
        "beam.internal_forces",
        "beam",
        "Loaded beam above aligned N, V and M diagrams with jumps, extrema, zeros and signs.",
        ("graphical", "solution"),
        _beam_internal_forces,
    )
)
register_generator(
    Generator(
        "beam.virtual_work",
        "beam",
        "Unit-load method: real loading and M above the unit virtual loading and m (settings.virtual); "
        "the displacement from int M m/EI dx is checked against the elastic line.",
        ("solution", "graphical"),
        _beam_virtual_work,
    )
)
register_generator(
    Generator("beam.deflection", "beam", "Elastic line (needs EI), exaggerated, with the extreme deflections.", ("graphical", "solution"), _beam_deflection)
)

register_conventions(PRESETS)


# --------------------------------------------------------------------------- sections

from studium.engineering.structures import section_draw  # noqa: E402
from studium.engineering.structures.section import parse_section, section_data, solve_section, verify_section  # noqa: E402


def _section_check(spec: dict[str, object], claims: object) -> tuple[dict[str, object], Evidence]:
    solution = solve_section(parse_section(spec))
    return section_data(solution), verify_section(solution, claims)


def _section_properties(spec, settings, options, claims) -> Generated:
    solution = solve_section(parse_section(spec))
    tikz = section_draw.properties_figure(solution, comma=options.comma)
    evidence = verify_section(solution, claims)
    evidence.extend(section_draw.verify_section_drawing(tikz, solution))
    return Generated(tikz, section_data(solution), evidence)


def _section_stress(spec, settings, options, claims) -> Generated:
    solution = solve_section(parse_section(spec))
    tikz = section_draw.stress_figure(solution, comma=options.comma)
    evidence = verify_section(solution, claims)
    evidence.extend(section_draw.verify_section_drawing(tikz, solution))
    return Generated(tikz, section_data(solution), evidence)


register_family(
    Family(
        "section",
        "Cross-section made of rectangles and polygons (holes allowed): area, centroid, Iz, Iy, Iyz, principal "
        "axes; with loads N, My, Mz the normal-stress field, neutral axis and extreme stresses.",
        _section_check,
    )
)
register_generator(
    Generator("section.properties", "section", "Section with centroid, centroidal and principal axes and overall dimensions.", ("statement", "model", "solution"), _section_properties)
)
register_generator(
    Generator("section.stress", "section", "Normal-stress field: neutral axis, tension and compression zones, extreme stresses.", ("graphical", "solution"), _section_stress)
)


# --------------------------------------------------------------------------- thin-walled sections

from studium.engineering.structures import thinwall_draw  # noqa: E402
from studium.engineering.structures.thinwall import parse_thin_wall, solve_thin_wall, thin_wall_data, verify_thin_wall  # noqa: E402


def _thin_wall_check(spec: dict[str, object], claims: object) -> tuple[dict[str, object], Evidence]:
    solution = solve_thin_wall(parse_thin_wall(spec))
    return thin_wall_data(solution), verify_thin_wall(solution, claims)


def _thin_wall_geometry(spec, settings, options, claims) -> Generated:
    solution = solve_thin_wall(parse_thin_wall(spec))
    tikz = thinwall_draw.geometry_figure(solution, comma=options.comma)
    evidence = verify_thin_wall(solution, claims)
    return Generated(tikz, thin_wall_data(solution), evidence)


def _thin_wall_flow(spec, settings, options, claims) -> Generated:
    solution = solve_thin_wall(parse_thin_wall(spec))
    tikz = thinwall_draw.flow_figure(solution, comma=options.comma)
    evidence = verify_thin_wall(solution, claims)
    evidence.extend(thinwall_draw.verify_flow_drawing(tikz, solution))
    return Generated(tikz, thin_wall_data(solution), evidence)


register_family(
    Family(
        "thin_wall",
        "Thin-walled section of straight walls (open, closed or multicell; optional booms): shear flow under "
        "Vy, Vz applied at a point or at the shear centre, torque, shear centre, twist rate.",
        _thin_wall_check,
    )
)
register_generator(
    Generator("thin_wall.geometry", "thin_wall", "Walls with thickness, nodes, booms, cells, centroid G and shear centre C, applied shear.", ("statement", "model"), _thin_wall_geometry)
)
register_generator(
    Generator("thin_wall.shear_flow", "thin_wall", "Shear-flow distribution q(s) drawn on every wall with its direction and nodal values.", ("graphical", "solution"), _thin_wall_flow)
)


# --------------------------------------------------------------------------- stress states

from studium.engineering.structures import stress as stress_module  # noqa: E402


def _stress_check(spec: dict[str, object], claims: object) -> tuple[dict[str, object], Evidence]:
    solution = stress_module.solve_stress(stress_module.parse_stress(spec))
    return stress_module.stress_data(solution), stress_module.verify_stress(solution, claims)


def _stress_mohr(spec, settings, options, claims) -> Generated:
    solution = stress_module.solve_stress(stress_module.parse_stress(spec))
    tikz = stress_module.mohr_figure(solution, comma=options.comma)
    evidence = stress_module.verify_stress(solution, claims)
    evidence.extend(stress_module.verify_mohr_drawing(tikz, solution))
    return Generated(tikz, stress_module.stress_data(solution), evidence)


def _stress_element(spec, settings, options, claims) -> Generated:
    solution = stress_module.solve_stress(stress_module.parse_stress(spec))
    tikz = stress_module.element_figure(solution, comma=options.comma)
    return Generated(tikz, stress_module.stress_data(solution), stress_module.verify_stress(solution, claims))


register_family(
    Family(
        "stress_state",
        "Plane stress state (sigma_x, sigma_y, tau_xy, optional sigma_z): principal stresses and directions, "
        "maximum shear, von Mises and Tresca, stresses on a rotated element.",
        _stress_check,
    )
)
register_generator(
    Generator("stress_state.mohr", "stress_state", "Mohr's circle (and the three circles of the 3D state) with face points, principal stresses, tau_max and 2 theta_p.", ("graphical", "solution"), _stress_mohr)
)
register_generator(
    Generator("stress_state.element", "stress_state", "Stress element on the x, y faces and the principal element rotated by theta_p.", ("statement", "solution"), _stress_element)
)
