#!/usr/bin/env python3
"""Build the Spanish fluid-mechanics example book under examples/.

This script recreates ``examples/fluid-mechanics-ule`` from source texts that
were actually retrieved on 2026-10-09 from the URLs listed below. It never
calls the network and never calls an external model: the book, its audits,
its computations and its worked problems are produced offline by the Studium
authoring pipeline itself.

Usage:
    source venv/bin/activate
    python examples/build-fluid-mechanics-ule.py [--keep]

With ``--keep`` the previous ``examples/fluid-mechanics-ule`` directory is
kept and the pipeline appends to it (the driver is only idempotent when it
starts from an empty book). Without it the directory is recreated from
scratch, which is the reproducible default.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))

from studium.authoring.computation import evaluate  # noqa: E402
from studium.authoring.render import find_engine, render_draft  # noqa: E402
from studium.cli.app import main  # noqa: E402
from studium.mcp.server import dispatch, open_workspace  # noqa: E402

EXAMPLES = _REPO / "examples"
BOOK = EXAMPLES / "fluid-mechanics-ule"
SLUG = "fluid-mechanics-ule"

COURSE = {
    "course": "Mecánica de Fluidos",
    "university": "Universidad de León",
    "degree": "Grado en Ingeniería Aeroespacial",
}

BLUEPRINT = [
    {"id": "propiedades", "title": "Propiedades de los fluidos: densidad y viscosidad"},
    {"id": "estatica", "title": "Estática de fluidos: presión hidrostática y principio de Arquímedes"},
    {"id": "continuidad", "title": "Cinemática: ecuación de continuidad y conservación de la masa"},
    {"id": "bernoulli", "title": "Ecuación de Bernoulli y aplicaciones del flujo ideal"},
    {"id": "reynolds", "title": "Análisis dimensional y número de Reynolds"},
    {"id": "tuberias", "title": "Flujo en conductos: régimen laminar y turbulento"},
    {"id": "capa-limite", "title": "Capa límite, sustentación y resistencia aerodinámica"},
    {"id": "aplicaciones", "title": "Aplicaciones aeroespaciales de la mecánica de fluidos"},
]

# Every ``text`` is a verbatim fragment of the page retrieved on 2026-10-09.
# Wikipedia and LibreTexts quotes are short (one or two sentences); NASA
# pages are public domain; the ULE line is the factual course table of the
# public plan-de-estudios page.
SOURCES = [
    {
        "id": "ule-plan",
        "title": "Universidad de León — Plan de estudios del Grado en Ingeniería Aeroespacial, asignatura 0710311 Mecánica de Fluidos",
        "url": "https://www.unileon.es/estudiantes/oferta-academica/grados/grado-en-ingenieria-aeroespacial/plan-estudios?id=0710311&cursoa=2022",
        "license": "Página pública de la universidad (datos de plan de estudios)",
        "text": (
            "MECÁNICA DE FLUIDOS — Grado en Ingeniería Aeroespacial — código 0710311 — 6 ECTS — "
            "S1 — OB — Departamento: QUIMICA Y FISICA APLICADAS — Área: FISICA APLICADA — "
            "Nombre en inglés: FLUID MECHANICS."
        ),
    },
    {
        "id": "nasa-bern",
        "title": "Bernoulli's Equation — NASA Glenn Research Center (Beginner's Guide to Aeronautics)",
        "url": "https://www.grc.nasa.gov/www/k-12/airplane/bern.html",
        "license": "Dominio público (NASA)",
        "text": (
            "In the 1700s, Daniel Bernoulli investigated the forces present in a moving fluid. "
            "The equation states that the static pressure ps in the flow plus the dynamic pressure, "
            "one half of the density r times the velocity V squared, is equal to a constant "
            "throughout the flow. We call this constant the total pressure pt of the flow. "
            "The static pressure integrated along the entire surface of the airfoil gives the total "
            "aerodynamic force on the foil. This force can be broken down into the lift and drag of "
            "the airfoil. Bernoulli's equation is also used on aircraft to provide a speedometer "
            "called a pitot-static tube; in a pitot-static tube, we measure the static and total "
            "pressure and can then use Bernoulli's equation to compute the velocity."
        ),
    },
    {
        "id": "nasa-reynolds",
        "title": "Reynolds Number — NASA Glenn Research Center (Beginner's Guide to Aeronautics)",
        "url": "https://www.grc.nasa.gov/www/k-12/airplane/reynolds.html",
        "license": "Dominio público (NASA)",
        "text": (
            "The important similarity parameter for viscosity is the Reynolds number. "
            "The Reynolds number expresses the ratio of inertial (resistant to change or motion) "
            "forces to viscous (heavy and gluey) forces. The Reynolds number is a dimensionless "
            "number. High values of the parameter (on the order of 10 million) indicate that "
            "viscous forces are small and the flow is essentially inviscid. Low values of the "
            "parameter (on the order of 1 hundred) indicate that viscous forces must be considered."
        ),
    },
    {
        "id": "nasa-viscosity",
        "title": "Viscosity — NASA Glenn Research Center (Beginner's Guide to Aeronautics)",
        "url": "https://www.grc.nasa.gov/www/k-12/airplane/viscosity.html",
        "license": "Dominio público (NASA)",
        "text": (
            "As an object moves through a gas, the gas molecules near the object are disturbed and "
            "move around the object. Aerodynamic forces are generated between the gas and the "
            "object. The magnitude of these forces depend on the shape of the object, the speed of "
            "the object, the mass of the gas going by the object and on two other important "
            "properties of the gas; the viscosity, or stickiness, of the gas and the "
            "compressibility, or springiness, of the gas. On this page, we examine the viscosity "
            "of a gas. The dynamic viscosity coefficient divided by the density is called the "
            "kinematic viscosity and given the Greek symbol nu. The units of nu are length^2/sec."
        ),
    },
    {
        "id": "nasa-boundary",
        "title": "Boundary Layer — NASA Glenn Research Center (Beginner's Guide to Aeronautics)",
        "url": "https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/boundary-layer/",
        "license": "Dominio público (NASA)",
        "text": (
            "This creates a thin layer of fluid near the surface in which the velocity changes from "
            "zero at the surface to the free stream value away from the surface. Engineers call "
            "this layer the boundary layer because it occurs on the boundary of the fluid. "
            "The displacement thickness depends on the Reynolds number, which is the ratio of "
            "inertial (resistant to change or motion) forces to viscous (heavy and gluey) forces. "
            "Boundary layers may be either laminar (layered), or turbulent (disordered) depending "
            "on the value of the Reynolds number. Flow separation is the reason for wing stall at "
            "high angle of attack. The theory which describes boundary layer effects was first "
            "presented by Ludwig Prandtl in the early 1900's."
        ),
    },
    {
        "id": "wiki-bernoulli",
        "title": "Principio de Bernoulli — Wikipedia en español",
        "url": "https://es.wikipedia.org/wiki/Principio_de_Bernoulli",
        "license": "CC BY-SA 4.0 (Wikipedia)",
        "text": (
            "En dinámica de fluidos, el principio de Bernoulli, también denominado ecuación de "
            "Bernoulli, describe el comportamiento de un fluido moviéndose a lo largo de una línea "
            "de corriente. Fue expuesto por Daniel Bernoulli en su obra Hidrodinámica (1738)."
        ),
    },
    {
        "id": "wiki-viscosidad",
        "title": "Viscosidad — Wikipedia en español",
        "url": "https://es.wikipedia.org/wiki/Viscosidad",
        "license": "CC BY-SA 4.0 (Wikipedia)",
        "text": (
            "La viscosidad de un fluido es una medida de su resistencia a las deformaciones "
            "graduales producidas por tensiones cortantes o tensiones de tracción en un fluido. "
            "Por ejemplo, la miel tiene una viscosidad dinámica mucho mayor que la del agua. "
            "La viscosidad dinámica de la miel es 70 centipoises y la viscosidad dinámica del agua "
            "es 1 centipoise a temperatura ambiente."
        ),
    },
    {
        "id": "wiki-reynolds",
        "title": "Número de Reynolds — Wikipedia en español",
        "url": "https://es.wikipedia.org/wiki/N%C3%BAmero_de_Reynolds",
        "license": "CC BY-SA 4.0 (Wikipedia)",
        "text": (
            "El número de Reynolds (Re) es un número adimensional utilizado en mecánica de fluidos "
            "y en fenómenos de transporte para caracterizar el movimiento de un fluido. Su valor "
            "indica si el flujo sigue un modelo laminar o turbulento."
        ),
    },
    {
        "id": "wiki-continuidad",
        "title": "Ecuación de continuidad — Wikipedia en español",
        "url": "https://es.wikipedia.org/wiki/Ecuaci%C3%B3n_de_continuidad",
        "license": "CC BY-SA 4.0 (Wikipedia)",
        "text": (
            "En física, una ecuación de continuidad expresa una ley de conservación de forma "
            "matemática, ya sea de forma integral como de forma diferencial. Dado que la masa, la "
            "energía, el impulso, la carga eléctrica y otras cantidades naturales se conservan en "
            "sus respectivas condiciones adecuadas, se pueden describir diversos fenómenos físicos "
            "utilizando ecuaciones de continuidad."
        ),
    },
    {
        "id": "wiki-presion",
        "title": "Presión en un fluido — Wikipedia en español",
        "url": "https://es.wikipedia.org/wiki/Presi%C3%B3n_en_un_fluido",
        "license": "CC BY-SA 4.0 (Wikipedia)",
        "text": (
            "La presión que ejerce el líquido es la presión termodinámica que interviene en la "
            "ecuación constitutiva y en la ecuación de movimiento del fluido, en algunos casos "
            "especiales esta presión coincide con la presión media o incluso con la presión "
            "hidrostática. Todas las presiones representan una medida de la energía potencial por "
            "unidad de volumen en un fluido."
        ),
    },
    {
        "id": "wiki-arquimedes",
        "title": "Principio de Arquímedes — Wikipedia en español",
        "url": "https://es.wikipedia.org/wiki/Principio_de_Arqu%C3%ADmedes",
        "license": "CC BY-SA 4.0 (Wikipedia)",
        "text": (
            "El principio de Arquímedes es el principio físico que afirma: «Un cuerpo total o "
            "parcialmente sumergido en un fluido en reposo experimenta un empuje vertical hacia "
            "arriba igual al peso del fluido desalojado». El principio de Arquímedes se expresa "
            "mediante la siguiente fórmula: E = Pe V = ρf g V."
        ),
    },
    {
        "id": "wiki-laminar",
        "title": "Flujo laminar — Wikipedia en español",
        "url": "https://es.wikipedia.org/wiki/Flujo_laminar",
        "license": "CC BY-SA 4.0 (Wikipedia)",
        "text": (
            "Se llama flujo laminar o corriente laminar al movimiento de un fluido cuando este es "
            "ordenado, estratificado o suave. En un flujo laminar, el fluido se mueve en láminas "
            "paralelas sin entremezclarse y cada partícula de fluido sigue una trayectoria suave, "
            "llamada línea de corriente. En flujos laminares, el mecanismo de transporte lateral es "
            "exclusivamente molecular. El flujo laminar es típico de fluidos a velocidades bajas o "
            "viscosidades altas, mientras que flujos de fluidos de viscosidad baja, velocidad alta "
            "o grandes caudales suelen ser turbulentos."
        ),
    },
    {
        "id": "libretexts-bern",
        "title": "11.3: Ecuación de Bernoulli — LibreTexts Español (Física sin límites)",
        "url": "https://espanol.libretexts.org/Bookshelves/Fisica/Libro%3A_Fisica_(sin_limites)/11%3A_La_din%C3%A1mica_de_fluidos_y_sus_aplicaciones/11.3%3A_Ecuaci%C3%B3n_de_Bernoulli",
        "license": "CC BY-SA 4.0 (LibreTexts / Lumen Learning)",
        "text": (
            "La ecuación de Bernoulli establece que para un fluido incompresible e inviscido, la "
            "energía mecánica total del fluido es constante."
        ),
    },
    {
        "id": "mit-ocw",
        "title": "Advanced Fluid Mechanics (2.25) — MIT OpenCourseWare, Fall 2013",
        "url": "https://ocw.mit.edu/courses/2-25-advanced-fluid-mechanics-fall-2013/",
        "license": "CC BY-NC-SA 4.0 (MIT OpenCourseWare)",
        "text": (
            "The Continuum Viewpoint and the Equations of Motion; Fluid Statics; Inviscid Flow and "
            "Bernoulli; Control Volume Theorems and Applications; Equations of Viscous Flow; "
            "Dimensional Analysis."
        ),
    },
]

# Section data: paragraphs (original Spanish prose), evidence excerpt ids,
# optional computation expression and optional numeric problem prompt.
SECTIONS = {
    "propiedades": {
        "excerpts": ["nasa-viscosity", "wiki-viscosidad", "nasa-reynolds"],
        "paragraphs": [
            (
                "La mecánica de fluidos estudia el comportamiento de los líquidos y de los gases en "
                "reposo y en movimiento, así como las fuerzas que ese movimiento origina sobre los "
                "cuerpos que los contienen o que se desplazan a través de ellos. Se considera fluido "
                "toda sustancia capaz de deformarse de manera continua bajo la acción de un esfuerzo "
                "cortante, por pequeño que este sea. En un fluido en reposo solo aparecen tensiones "
                "normales, mientras que durante el movimiento surgen además tensiones tangenciales "
                "que se oponen al deslizamiento relativo de las capas vecinas."
            ),
            (
                "La viscosidad dinámica mide la resistencia de un fluido a las deformaciones "
                "graduales producidas por tensiones cortantes o de tracción, como explica la versión "
                "española de Wikipedia. La NASA describe la viscosidad, a la que llama pegajosidad o "
                "stickiness del gas, como una de las propiedades que, junto con la forma del objeto, "
                "la velocidad y la masa del fluido, determinan la magnitud de las fuerzas "
                "aerodinámicas. A temperatura ambiente el agua presenta una viscosidad dinámica de 1 "
                "centipoise, mientras que la miel alcanza valores del orden de 70 centipoises, de "
                "modo que opone mucha más resistencia a fluir."
            ),
        ],
    },
    "estatica": {
        "excerpts": ["wiki-presion", "wiki-arquimedes"],
        "paragraphs": [
            (
                "En un fluido en reposo la presión hidrostática crece con la profundidad porque cada "
                "punto soporta el peso de las capas de fluido situadas por encima. La presión que "
                "ejerce el líquido es la presión termodinámica que interviene en la ecuación "
                "constitutiva y en la ecuación de movimiento del fluido; en algunos casos especiales "
                "coincide con la presión media o incluso con la presión hidrostática propiamente "
                "dicha. Todas las presiones representan una medida de la energía potencial por "
                "unidad de volumen del fluido."
            ),
            (
                "El principio de Arquímedes afirma que todo cuerpo total o parcialmente sumergido en "
                "un fluido en reposo experimenta un empuje vertical hacia arriba igual al peso del "
                "fluido desalojado. Este empuje hidrostático, medido en newtons, se expresa como el "
                "producto de la densidad del fluido, la aceleración de la gravedad y el volumen "
                "desalojado. Sobre esta ley se apoyan la flotación de los barcos, la estabilidad de "
                "los globos y dirigibles y los problemas de flotabilidad de los cuerpos sumergidos."
            ),
        ],
        "computation": {
            "expression": "998*9.81*10",
            "note": "Presión hidrostática ρ g h en pascales con h = 10 m, ρ = 998 kg/m³, g = 9,81 m/s².",
        },
        "problem": {
            "prompt": (
                "Presión hidrostática en agua dulce a diez metros de profundidad. Sabiendo que la "
                "densidad es ρ = 998 kg/m³, que la gravedad es g = 9,81 m/s² y que la profundidad es "
                "h = 10 m, calcula el producto ρ g h en pascales con la expresión 998*9.81*10. "
                "Escribe el resultado como fracción exacta."
            ),
        },
    },
    "continuidad": {
        "excerpts": ["wiki-continuidad", "mit-ocw"],
        "paragraphs": [
            (
                "La ecuación de continuidad expresa matemáticamente una ley de conservación, ya sea "
                "en forma integral o en forma diferencial. Como la masa, la energía, el impulso y la "
                "carga eléctrica se conservan en sus respectivas condiciones, son muchos los "
                "fenómenos físicos que pueden describirse mediante ecuaciones de continuidad. En "
                "mecánica de fluidos la versión más habitual relaciona la variación temporal de la "
                "densidad con la divergencia del flujo másico, es decir, del producto de la densidad "
                "por el campo de velocidades."
            ),
            (
                "Para un fluido incompresible la densidad permanece constante y la ecuación de "
                "continuidad se reduce a la anulación de la divergencia del campo de velocidades: el "
                "fluido no puede acumularse ni agotarse en ningún punto. La conservación de la masa "
                "obliga además a que el caudal que atraviesa una sección sea el mismo en todas las "
                "secciones del conducto cuando el régimen es permanente. Un estrechamiento impone "
                "entonces una aceleración del flujo, idea que está en la base del medidor de Venturi."
            ),
        ],
    },
    "bernoulli": {
        "excerpts": ["nasa-bern", "wiki-bernoulli", "libretexts-bern"],
        "problem_excerpts": ["nasa-bern", "wiki-bernoulli"],
        "paragraphs": [
            (
                "La ecuación de Bernoulli describe el comportamiento de un fluido ideal, es decir, "
                "incompresible y sin viscosidad, que se mueve a lo largo de una línea de corriente. "
                "La NASA la presenta como la suma de la presión estática y de la presión dinámica, "
                "que resulta ser igual a una constante a la que llama presión total del flujo. A lo "
                "largo de la línea de corriente la energía del fluido permanece constante: lo que el "
                "flujo gana en velocidad lo pierde en presión, y al contrario."
            ),
            (
                "La versión española de Wikipedia sitúa el enunciado del principio en la obra "
                "Hidrodinámica de Daniel Bernoulli, publicada en 1738, y la página de LibreTexts "
                "Español recuerda que la ecuación se aplica a fluidos incompresibles e inviscidos, en "
                "los que la energía mecánica total permanece constante. Cuando se añade el término "
                "de posición, la suma de la presión estática, la presión dinámica y el término que "
                "depende de la altura se mantiene constante a lo largo del flujo. Una consecuencia "
                "práctica es que en un medidor de Venturi la presión cae donde la velocidad aumenta, "
                "fenómeno que también explica la fuerza de sustentación sobre los perfiles de ala."
            ),
        ],
        "computation": {
            "expression": "2*9.81*5",
            "note": "Energía cinética por unidad de masa v² = 2 g h de la ley de Torricelli con h = 5 m y g = 9,81 m/s².",
        },
        "problem": {
            "prompt": (
                "Ley de Torricelli para un orificio de salida. Si un depósito tiene un orificio a "
                "una profundidad h = 5 m por debajo de la superficie libre y la gravedad vale "
                "g = 9,81 m/s², calcula la energía cinética por unidad de masa, igual a dos por g "
                "por h, con la expresión 2*9.81*5. El resultado se expresa en metros cuadrados "
                "por segundo cuadrado."
            ),
        },
    },
    "reynolds": {
        "excerpts": ["nasa-reynolds", "wiki-reynolds", "nasa-boundary"],
        "problem_excerpts": ["nasa-reynolds", "wiki-reynolds"],
        "paragraphs": [
            (
                "El número de Reynolds es un número adimensional que compara las fuerzas de inercia "
                "con las fuerzas viscosas presentes en un flujo. La NASA explica que las fuerzas de "
                "inercia se caracterizan por el producto de la densidad, la velocidad y el gradiente "
                "de velocidad, mientras que las fuerzas viscosas dependen del coeficiente de "
                "viscosidad dinámica y de la segunda derivada del campo de velocidades. Valores "
                "altos del parámetro indican que las fuerzas viscosas son pequeñas frente a las de "
                "inercia, mientras que valores bajos obligan a considerarlas."
            ),
            (
                "En forma simplificada, el número de Reynolds es el cociente entre el producto de la "
                "densidad, la velocidad y una longitud característica y la viscosidad dinámica, como "
                "recoge la página de la NASA sobre la capa límite. El valor del parámetro determina "
                "si el flujo se comporta como laminar o como turbulento; la versión española de "
                "Wikipedia indica que su valor señala cuál de los dos modelos describe mejor el "
                "movimiento del fluido. Por eso se utiliza como parámetro de similitud para "
                "reproducir en túneles de viento las condiciones reales de vuelo a escala."
            ),
        ],
        "computation": {
            "expression": "998*2*0.1/0.001",
            "note": "Número de Reynolds ρ V D / μ para agua a 20 °C con V = 2 m/s, D = 0,1 m, ρ = 998 kg/m³ y μ = 0,001 Pa·s.",
        },
        "problem": {
            "prompt": (
                "Número de Reynolds del agua en una tubería. Para agua a 20 °C que circula a 2 m/s "
                "por una tubería de 0,1 m de diámetro, con densidad ρ = 998 kg/m³ y viscosidad "
                "dinámica μ = 0,001 Pa·s, calcula el producto ρ V D dividido por μ con la expresión "
                "998*2*0.1/0.001. El resultado es un número adimensional."
            ),
        },
    },
    "tuberias": {
        "excerpts": ["wiki-laminar", "wiki-reynolds", "nasa-reynolds"],
        "paragraphs": [
            (
                "En un flujo laminar dentro de una tubería el fluido se mueve en láminas "
                "concéntricas que no se entremezclan: cada partícula sigue una trayectoria suave, el "
                "perfil de velocidades resulta parabólico, con velocidad máxima en el eje y "
                "velocidad nula en la pared, y el transporte lateral de cantidad de movimiento es "
                "exclusivamente molecular. El régimen laminar es típico de fluidos a velocidades "
                "bajas o con viscosidades altas, mientras que las viscosidades bajas, las "
                "velocidades altas y los caudales grandes favorecen la turbulencia."
            ),
            (
                "Cuando el número de Reynolds aumenta, el flujo pierde estabilidad: aparecen "
                "ondulaciones irregulares que evolucionan hacia un régimen turbulento, caracterizado "
                "por movimientos desordenados, no estacionarios y tridimensionales. La experiencia "
                "acumulada sitúa la transición en conductos circulares entre valores del parámetro "
                "próximos a 2300 y 4000, con una zona intermedia de comportamiento incierto. La "
                "rugosidad de la pared y el estado de la corriente de entrada pueden adelantar o "
                "retrasar esa transición."
            ),
        ],
    },
    "capa-limite": {
        "excerpts": ["nasa-boundary", "nasa-reynolds", "mit-ocw"],
        "paragraphs": [
            (
                "Junto a la superficie de un cuerpo que se mueve en un fluido se forma una capa "
                "delgada en la que la velocidad pasa de cero, en la pared, al valor de la corriente "
                "libre, fuera de ella. La NASA explica que las moléculas adheridas a la superficie "
                "frenan por colisiones a las capas inmediatamente superiores, de modo que el espesor "
                "característico de esa capa límite depende del número de Reynolds. La teoría que "
                "describe estos efectos fue presentada por Ludwig Prandtl a comienzos del siglo XX y "
                "hoy es un tema habitual en los cursos avanzados de mecánica de fluidos."
            ),
            (
                "La capa límite puede ser laminar o turbulenta según el valor del número de "
                "Reynolds: a números bajos el flujo está estratificado y la velocidad varía de forma "
                "uniforme al alejarse de la pared, mientras que a números altos aparecen remolinos "
                "no estacionarios dentro de la capa. Cuando el flujo próximo a la pared pierde "
                "energía, la capa puede separarse del contorno y crear una estela que modifica la "
                "forma efectiva del cuerpo. La separación del flujo es la razón de la entrada en "
                "pérdida del ala en ángulos de ataque elevados, y sus efectos se reflejan en los "
                "coeficientes de sustentación y de resistencia."
            ),
        ],
    },
    "aplicaciones": {
        "excerpts": ["ule-plan", "mit-ocw", "libretexts-bern", "nasa-bern"],
        "paragraphs": [
            (
                "La asignatura Mecánica de Fluidos del Grado en Ingeniería Aeroespacial de la "
                "Universidad de León se imparte en el primer semestre con 6 créditos ECTS y carácter "
                "obligatorio, dentro del área de Física Aplicada del departamento de Química y "
                "Física Aplicadas, y figura en el plan de estudios con el código 0710311 y el nombre "
                "en inglés Fluid Mechanics. El temario se apoya en las bases de estática, "
                "cinemática y dinámica de fluidos que desarrollan las secciones anteriores de este "
                "libro."
            ),
            (
                "La NASA explica que la presión estática integrada a lo largo de la superficie de un "
                "perfil da la fuerza aerodinámica total, que se descompone en sustentación y "
                "resistencia, y describe cómo un tubo de Pitot estático mide las presiones estática "
                "y total para calcular la velocidad del avión. El curso Advanced Fluid Mechanics del "
                "MIT dedica capítulos a la estática de fluidos, al flujo no viscoso y a la ecuación "
                "de Bernoulli, a las ecuaciones de flujo viscoso y al análisis dimensional. Estos "
                "temas completan la formación básica que aquí se presenta."
            ),
        ],
    },
}


def _record_source_and_excerpt(session, item: dict[str, object]) -> str:
    source = dispatch(
        "studium_public_source_record",
        {"title": item["title"], "url": item["url"], "text": item["text"]},
        session=session,
    )
    assert source["status"] == "recorded", source
    source_id = source["candidate"]["id"]
    opened = dispatch(
        "studium_public_source_open_supplement",
        {"id": source_id, "open_supplement": True, "open_licensed": True},
        session=session,
    )
    assert opened["status"] in {"recorded", "ok", "unchanged", "already_recorded"} or opened.get(
        "open_supplement"
    ) is True, opened
    excerpt = dispatch(
        "studium_excerpt_record",
        {"source_id": source_id, "url": item["url"], "text": item["text"]},
        session=session,
    )
    assert excerpt["status"] == "recorded", excerpt
    return str(excerpt["excerpt"]["id"])


def _paragraph(session, section: str, text: str, excerpt_ids: list[str]) -> str:
    recorded = dispatch(
        "studium_paragraph_record",
        {"section": section, "text": text, "excerpts": excerpt_ids, "role": "explanation"},
        session=session,
    )
    assert recorded["status"] == "recorded", recorded
    return str(recorded["paragraph"]["id"])


def _decimal_answer(value) -> str:
    """A float-parseable string for the problem 'expected' field."""
    if value.denominator == 1:
        return str(value.numerator)
    return f"{float(value):.12g}"


def _computation(session, section: str, expression: str) -> tuple[str, str]:
    expected = str(evaluate(expression))
    checked = dispatch(
        "studium_computation_check",
        {"expression": expression, "result": expected, "section": section},
        session=session,
    )
    assert checked["status"] == "replayed", checked
    assert checked["correct"] is True, checked
    assert checked["server_result"] == expected, checked
    return str(checked["computation"]["id"]), expected


def _problem(session, section: str, prompt: str, expected: str, excerpt_ids: list[str]) -> str:
    recorded = dispatch(
        "studium_problem_record",
        {"section": section, "prompt": prompt, "expected": expected, "excerpts": excerpt_ids},
        session=session,
    )
    if recorded.get("problem", {}).get("status") != "two_witnesses":
        raise AssertionError(f"problem not two_witnesses: {json.dumps(recorded, ensure_ascii=False)[:1200]}")
    return str(recorded["problem"]["id"])


def _audit(session, target: str, excerpt_ids: list[str], computation_id: str | None = None) -> dict[str, object]:
    params: dict[str, object] = {"target": target, "kind": "scientific", "excerpts": excerpt_ids}
    if computation_id is not None:
        params["computation"] = computation_id
    audited = dispatch("studium_audit_record", params, session=session)
    assert audited["status"] == "recorded", audited
    if computation_id is not None:
        assert audited["audit"]["evidence"]["computation_result"] == "COMPUTATION_REPRODUCED", audited
    return audited


def build() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", action="store_true", help="keep the existing book directory")
    args = parser.parse_args()

    EXAMPLES.mkdir(parents=True, exist_ok=True)
    if BOOK.exists() and not args.keep:
        shutil.rmtree(BOOK)

    code = main(
        [
            "create",
            SLUG,
            "--course",
            COURSE["course"],
            "--university",
            COURSE["university"],
            "--degree",
            COURSE["degree"],
            "--academic-year",
            "2025-2026",
            "--course-code",
            "0710311",
            "--semester",
            "S1",
            "--language",
            "es",
            "--profile",
            "STEM",
            "--project-dir",
            str(EXAMPLES),
        ]
    )
    assert code == 0, f"create exited with {code}"

    session = open_workspace(str(EXAMPLES))
    assert session is not None
    session.active = BOOK

    stored = dispatch("studium_blueprint_store", {"sections": BLUEPRINT}, session=session)
    assert stored["status"] == "recorded", stored

    excerpts: dict[str, str] = {}
    for item in SOURCES:
        excerpts[item["id"]] = _record_source_and_excerpt(session, item)

    computation_ids: dict[str, str] = {}
    problem_ids: dict[str, str] = {}
    paragraph_ids: dict[str, list[str]] = {}

    for section_id, section_data in SECTIONS.items():
        for text in section_data["paragraphs"]:
            paragraph_ids.setdefault(section_id, []).append(
                _paragraph(session, section_id, text, [excerpts[i] for i in section_data["excerpts"]])
            )
        if section_data.get("computation"):
            computation = section_data["computation"]
            computation_ids[section_id], raw_expected = _computation(
                session, section_id, computation["expression"]
            )
        if section_data.get("problem"):
            problem = section_data["problem"]
            problem_ids[section_id] = _problem(
                session,
                section_id,
                problem["prompt"],
                _decimal_answer(evaluate(computation["expression"])),
                [excerpts[i] for i in section_data.get("problem_excerpts", section_data["excerpts"][:2])],
            )

    for section_id, section_data in SECTIONS.items():
        _audit(
            session,
            section_id,
            [excerpts[i] for i in section_data["excerpts"]],
            computation_ids.get(section_id),
        )

    scanned = dispatch("studium_contradiction_scan", {}, session=session)
    assert scanned["open_count"] == 0, scanned
    reviewed = dispatch("studium_book_review", {}, session=session)
    assert reviewed["audit_passed"] is True, reviewed
    assert reviewed["released"] is False, reviewed

    rendered = render_draft(BOOK)
    assert rendered["status"] == "rendered", rendered

    pdf = BOOK / "latex" / "draft.pdf"
    assert pdf.is_file(), f"missing {pdf}"
    header = pdf.read_bytes()[:5]
    assert header == b"%PDF-", f"not a PDF: {header!r}"

    return 0


def write_documentation() -> None:
    """Document the example inside its own directory."""
    sources_public = []
    for item in SOURCES:
        sources_public.append({key: item[key] for key in ("id", "title", "url", "license", "text")})
    (BOOK / "sources.json").write_text(
        json.dumps({"retrieved_on": "2026-10-09", "sources": sources_public}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    readme = f"""# Mecánica de Fluidos — libro de ejemplo (ULE, Grado en Ingeniería Aeroespacial)

Este directorio es un libro de ejemplo construido por el pipeline de autoría de
Studium, en español, para el plan de estudios de la asignatura **0710311
Mecánica de Fluidos** (6 ECTS, S1, obligatoria, Área de Física Aplicada) del
**Grado en Ingeniería Aeroespacial de la Universidad de León**.

**No es un documento oficial de la universidad.** Es un índice de estudio
privado generado automáticamente.

## Qué contiene

- `project.toml` — ficha del curso y perfil (STEM, es).
- `bibliography/` — las 14 fuentes públicas registradas y sus excerptos.
- `blueprint/` — el esquema (outline) con las 8 secciones.
- `draft/` — párrafos, auditorías, escaneo de contradicciones y revisiones.
- `problems/` — comprobaciones aritméticas reproducidas y problemas numéricos.
- `latex/draft.pdf` — el PDF compilado de este libro.
- `sources.json` — lista de fuentes con URL, licencia y texto recogido.

## Cómo se construyó

```
source venv/bin/activate
python examples/build-fluid-mechanics-ule.py
```

El guion `../build-fluid-mechanics-ule.py` reproduce el libro sin red y sin
modelos externos: registra las fuentes, guarda el esquema de 8 secciones,
escribe los párrafos, reproduce las comprobaciones aritméticas (`expr = valor`
lo vuelve a evaluar el propio servidor), registra los problemas numéricos con
dos testimonios, audita cada sección, escanea contradicciones, revisa la
edición y compila `latex/draft.pdf` con LaTeX.

## Fuentes

Las 14 fuentes (URL y licencia en `sources.json`) se recuperaron el
2026-10-09. Los textos registrados son fragmentos verbatim cortos de esas
páginas: NASA Glenn (dominio público), Wikipedia en español (CC BY-SA 4.0),
LibreTexts Español (CC BY-SA 4.0) y MIT OpenCourseWare (CC BY-NC-SA 4.0). No
hay grandes pasajes protegidos por derechos de autor; las citas se limitan a
una o dos frases y el resto del texto es redacción original del libro.
"""
    (BOOK / "README.md").write_text(readme, encoding="utf-8")


if __name__ == "__main__":
    build()
    write_documentation()
    print(f"book ready: {BOOK}")
    print(f"pdf: {BOOK / 'latex' / 'draft.pdf'}")
    engine = find_engine()
    print(f"latex engine: {engine}")