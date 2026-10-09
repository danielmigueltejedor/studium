#!/usr/bin/env python3
"""Build the Spanish fluid-mechanics example book under examples/.

This script recreates ``examples/fluid-mechanics-ule`` from source texts that
were actually retrieved on 2026-10-09 from the URLs listed below. It never
calls the network and never calls an external model: the book, its depth plan,
its academic blueprint, its derivations, its audits, its computations and its
worked and practice problems are produced offline by the Studium authoring
pipeline itself.

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
import re
import shutil
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))

from studium.authoring.computation import evaluate  # noqa: E402
from studium.authoring.depth.length import LengthScope, assess_length_match  # noqa: E402
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

# Ten chapters, ordered from the fundamentals to measurement.
BLUEPRINT = [
    {"id": "introduccion", "title": "Introducción a la mecánica de fluidos"},
    {"id": "propiedades", "title": "Propiedades de los fluidos: densidad y viscosidad"},
    {"id": "estatica", "title": "Estática de fluidos: presión hidrostática y flotabilidad"},
    {"id": "continuidad", "title": "Cinemática: ecuación de continuidad"},
    {"id": "bernoulli", "title": "Dinámica: ecuación de Bernoulli y ley de Torricelli"},
    {"id": "momentum", "title": "Teorema del transporte de Reynolds y cantidad de movimiento"},
    {"id": "reynolds", "title": "Análisis dimensional y número de Reynolds"},
    {"id": "tuberias", "title": "Flujo viscoso en conductos: ley de Poiseuille"},
    {"id": "capa-limite", "title": "Capa límite, sustentación y resistencia aerodinámica"},
    {"id": "instrumentacion", "title": "Instrumentación: tubo de Pitot y manómetros"},
]

# One pair of learning concepts per chapter. The concept ids are used by the
# academic blueprint, by the paragraphs and by the exercises.
CONCEPTS = {
    "introduccion": [
        ("medio-continuo", "Hipótesis del medio continuo"),
        ("sistema-unidades", "Magnitudes y unidades"),
    ],
    "propiedades": [
        ("densidad", "Densidad y peso específico"),
        ("viscosidad-dinamica", "Viscosidad dinámica y cinemática"),
    ],
    "estatica": [
        ("presion-hidrostatica", "Presión hidrostática"),
        ("flotabilidad", "Flotabilidad"),
    ],
    "continuidad": [
        ("conservacion-masa", "Conservación de la masa"),
        ("caudal-volumetrico", "Caudal volumétrico"),
    ],
    "bernoulli": [
        ("ecuacion-bernoulli", "Ecuación de Bernoulli"),
        ("ley-torricelli", "Ley de Torricelli"),
    ],
    "momentum": [
        ("transporte-reynolds", "Teorema del transporte de Reynolds"),
        ("cantidad-movimiento", "Ecuación de la cantidad de movimiento"),
    ],
    "reynolds": [
        ("numero-reynolds", "Número de Reynolds"),
        ("similitud", "Similitud dinámica"),
    ],
    "tuberias": [
        ("flujo-laminar", "Régimen laminar"),
        ("ley-poiseuille", "Ley de Poiseuille"),
    ],
    "capa-limite": [
        ("capa-limite-concepto", "Capa límite"),
        ("espesor-desplazamiento", "Espesor de desplazamiento"),
    ],
    "instrumentacion": [
        ("tubo-pitot", "Tubo de Pitot"),
        ("manometro", "Manómetros"),
    ],
}

ACADEMIC_PARTS = [
    ("part-fundamentos", "Fundamentos", ["introduccion", "propiedades", "estatica"]),
    ("part-dinamica", "Dinámica de fluidos", ["continuidad", "bernoulli", "momentum"]),
    ("part-instrumentacion", "Flujo real e instrumentación", ["reynolds", "tuberias", "capa-limite", "instrumentacion"]),
]

# Every ``text`` is a verbatim fragment of the page retrieved on 2026-10-09.
# Wikipedia excerpts are short (one or two sentences) and the rest of the prose
# in the book is original. NASA pages are public domain; the ULE line is the
# factual course table of the public plan-de-estudios page.
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
        "url": (
            "https://espanol.libretexts.org/Bookshelves/Fisica/Libro%3A_Fisica_(sin_limites)/"
            "11%3A_La_din%C3%A1mica_de_fluidos_y_sus_aplicaciones/11.3%3A_Ecuaci%C3%B3n_de_Bernoulli"
        ),
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
    {
        "id": "wiki-navier-stokes",
        "title": "Ecuaciones de Navier-Stokes — Wikipedia en español",
        "url": "https://es.wikipedia.org/wiki/Ecuaciones_de_Navier-Stokes",
        "license": "CC BY-SA 4.0 (Wikipedia)",
        "text": (
            "En física, las ecuaciones de Navier-Stokes son un conjunto de ecuaciones en derivadas "
            "parciales no lineales que describen el movimiento de un fluido viscoso. Estas "
            "ecuaciones gobiernan la atmósfera terrestre, las corrientes oceánicas y el flujo "
            "alrededor de vehículos o proyectiles y, en general, cualquier fenómeno en el que se "
            "involucren fluidos newtonianos."
        ),
    },
    {
        "id": "wiki-rtt",
        "title": "Teorema del transporte de Reynolds — Wikipedia en español",
        "url": "https://es.wikipedia.org/wiki/Teorema_del_transporte_de_Reynolds",
        "license": "CC BY-SA 4.0 (Wikipedia)",
        "text": (
            "El teorema de transporte de Reynolds es un teorema fundamental utilizado en la "
            "formulación de las leyes básicas de la mecánica de fluidos, que relaciona la derivada "
            "lagrangiana de una integral de volumen de un sistema con una integral en derivadas "
            "eulerianas."
        ),
    },
    {
        "id": "wiki-poiseuille",
        "title": "Ley de Poiseuille — Wikipedia en español",
        "url": "https://es.wikipedia.org/wiki/Ley_de_Poiseuille",
        "license": "CC BY-SA 4.0 (Wikipedia)",
        "text": (
            "La ley de Poiseuille es una ley que permite determinar el flujo laminar estacionario de "
            "un líquido incompresible y uniformemente viscoso a través de un tubo cilíndrico de "
            "sección circular constante. La ley es también muy importante en hemodinámica."
        ),
    },
    {
        "id": "wiki-pitot",
        "title": "Tubo de Pitot — Wikipedia en español",
        "url": "https://es.wikipedia.org/wiki/Tubo_de_Pitot",
        "license": "CC BY-SA 4.0 (Wikipedia)",
        "text": (
            "El tubo de Pitot se utiliza para calcular la presión total, también denominada presión "
            "de estancamiento, presión remanente o presión de remanso."
        ),
    },
    {
        "id": "wiki-manometro",
        "title": "Manómetro — Wikipedia en español",
        "url": "https://es.wikipedia.org/wiki/Man%C3%B3metro",
        "license": "CC BY-SA 4.0 (Wikipedia)",
        "text": (
            "El manómetro es un instrumento de medición para la presión de fluidos contenidos en "
            "recipientes cerrados. Se distinguen dos tipos de manómetros, según se empleen para "
            "medir la presión de líquidos o de gases."
        ),
    },
    {
        "id": "wiki-turbulento",
        "title": "Flujo turbulento — Wikipedia en español",
        "url": "https://es.wikipedia.org/wiki/Flujo_turbulento",
        "license": "CC BY-SA 4.0 (Wikipedia)",
        "text": (
            "En mecánica de los fluidos, se llama flujo turbulento al movimiento de un fluido que "
            "se da en forma caótica, en el que las partículas se mueven desordenadamente y las "
            "trayectorias de las partículas se encuentran formando remolinos aperiódicos. Incluso "
            "en un flujo globalmente estacionario, la velocidad fluctúa alrededor del valor medio "
            "en las tres direcciones."
        ),
    },
    {
        "id": "wiki-capa-limite",
        "title": "Capa límite — Wikipedia en español",
        "url": "https://es.wikipedia.org/wiki/Capa_l%C3%ADmite",
        "license": "CC BY-SA 4.0 (Wikipedia)",
        "text": (
            "En mecánica de fluidos, la capa límite o capa fronteriza de un fluido es la zona donde "
            "el movimiento de este es perturbado por la presencia de un sólido con el que está en "
            "contacto por efecto de la viscosidad y la tensión cortante."
        ),
    },
]

# Section data: original Spanish prose, the sources that support it, and the
# pedagogical components that the pipeline records for each chapter.
SECTIONS: dict[str, dict[str, object]] = {
    "introduccion": {
        "excerpts": ["ule-plan", "mit-ocw", "wiki-navier-stokes"],
        "paragraphs": [
            (
                "La mecánica de fluidos estudia el movimiento de los líquidos y de los gases, así "
                "como las fuerzas que ese movimiento ejerce sobre los cuerpos que los contienen o "
                "que se desplazan a través de ellos. Para tratarla con las herramientas del cálculo "
                "se adopta la hipótesis del medio continuo: se supone que magnitudes como la "
                "densidad o la velocidad están definidas en cada punto del espacio y varían de forma "
                "suave, aunque a escala molecular el fluido esté formado por partículas discretas. "
                "Esta simplificación permite describir el fluido mediante campos continuos y "
                "aplicarles las leyes de conservación de la masa, la cantidad de movimiento y la "
                "energía."
            ),
            (
                "Las ecuaciones de Navier-Stokes son el modelo general que describe el movimiento "
                "de un fluido viscoso newtoniano y relacionan la aceleración del fluido con las "
                "fuerzas de presión, viscosidad y gravedad. La asignatura Mecánica de Fluidos del "
                "Grado en Ingeniería Aeroespacial de la Universidad de León, con código 0710311 y "
                "seis créditos ECTS, ordena estos contenidos desde la estática hasta el análisis "
                "dimensional. El curso avanzado de mecánica de fluidos del MIT recorre asimismo la "
                "estática, el flujo no viscoso, los teoremas de volumen de control, el flujo "
                "viscoso y el análisis dimensional, que es la secuencia que sigue este libro."
            ),
        ],
        "worked": {
            "prompt": (
                "Peso específico del aire. Para aire en condiciones estándar al nivel del mar, la "
                "densidad vale 1,225 kg/m³ y la gravedad 9,81 m/s². Calcula el peso específico, "
                "igual al producto de la densidad por la gravedad, con la expresión 1.225*9.81. El "
                "resultado se expresa en newtons por metro cúbico."
            ),
            "expression": "1.225*9.81",
            "excerpts": ["ule-plan", "mit-ocw"],
        },
        "practice": [
            {
                "prompt": (
                    "Peso específico del agua dulce. Con una densidad de 998 kg/m³ y una gravedad "
                    "de 9,81 m/s², calcula el producto de ambas magnitudes con la expresión "
                    "998*9.81. El resultado se expresa en newtons por metro cúbico."
                ),
                "expression": "998*9.81",
                "difficulty": "FOUNDATIONAL",
                "objectives": ["sistema-unidades"],
                "excerpts": ["ule-plan", "mit-ocw"],
            },
        ],
        "notation": [
            {"symbol": "t", "meaning": "tiempo", "units": "s"},
            {"symbol": "x", "meaning": "coordenada espacial", "units": "m"},
        ],
        "terminology": [
            {"term": "medio continuo", "definition": "hipótesis que describe el fluido mediante campos de magnitudes definidas en cada punto del espacio."},
        ],
    },
    "propiedades": {
        "excerpts": ["nasa-viscosity", "wiki-viscosidad", "nasa-reynolds"],
        "paragraphs": [
            (
                "En mecánica de fluidos se distingue entre líquidos y gases, que comparten la "
                "capacidad de deformarse de manera continua bajo la acción de un esfuerzo cortante. "
                "La densidad relaciona la masa con el volumen y el peso específico es el producto de "
                "la densidad por la aceleración de la gravedad. En un fluido en reposo solo aparecen "
                "tensiones normales, mientras que durante el movimiento surgen además tensiones "
                "tangenciales que se oponen al deslizamiento relativo de las capas vecinas."
            ),
            (
                "La viscosidad dinámica mide la resistencia de un fluido a las deformaciones "
                "graduales producidas por tensiones cortantes o de tracción, como explica la versión "
                "española de Wikipedia. La NASA describe la viscosidad, a la que llama pegajosidad "
                "del gas, como una de las propiedades que, junto con la forma del objeto, la "
                "velocidad y la masa del fluido, determinan la magnitud de las fuerzas "
                "aerodinámicas. El cociente entre la viscosidad dinámica y la densidad se denomina "
                "viscosidad cinemática; a temperatura ambiente el agua presenta una viscosidad "
                "dinámica mucho menor que la miel, de modo que esta última opone mucha más "
                "resistencia a fluir."
            ),
        ],
        "worked": {
            "prompt": (
                "Viscosidad cinemática del agua. Si la viscosidad dinámica del agua vale "
                "0,001 Pa·s y su densidad 998 kg/m³, calcula el cociente entre ambas con la "
                "expresión 0.001/998. El resultado se expresa en metros cuadrados por segundo."
            ),
            "expression": "0.001/998",
            "excerpts": ["nasa-viscosity", "wiki-viscosidad"],
        },
        "practice": [
            {
                "prompt": (
                    "Viscosidad cinemática del aire. Con una viscosidad dinámica de 0,0000181 Pa·s "
                    "y una densidad de 1,225 kg/m³, calcula el cociente entre ambas magnitudes con "
                    "la expresión 0.0000181/1.225."
                ),
                "expression": "0.0000181/1.225",
                "difficulty": "INTERMEDIATE",
                "objectives": ["viscosidad-dinamica"],
                "excerpts": ["nasa-viscosity", "nasa-reynolds"],
            },
        ],
        "notation": [
            {"symbol": "ρ", "meaning": "densidad del fluido", "units": "kg/m^3"},
            {"symbol": "μ", "meaning": "viscosidad dinámica", "units": "kg/(m*s)"},
            {"symbol": "ν", "meaning": "viscosidad cinemática", "units": "m^2/s"},
        ],
        "terminology": [
            {"term": "fluido newtoniano", "definition": "fluido cuya tensión cortante es proporcional al gradiente de velocidad."},
            {"term": "viscosidad cinemática", "definition": "cociente entre la viscosidad dinámica y la densidad del fluido."},
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
        "worked": {
            "prompt": (
                "Presión hidrostática en agua dulce a diez metros de profundidad. Sabiendo que la "
                "densidad es 998 kg/m³, que la gravedad es 9,81 m/s² y que la profundidad es 10 m, "
                "calcula el producto de las tres magnitudes con la expresión 998*9.81*10. El "
                "resultado se expresa en pascales."
            ),
            "expression": "998*9.81*10",
            "excerpts": ["wiki-presion", "wiki-arquimedes"],
        },
        "practice": [
            {
                "prompt": (
                    "Presión hidrostática a veinte metros de profundidad. Con la misma densidad y "
                    "gravedad, calcula el producto correspondiente a 20 m con la expresión "
                    "998*9.81*20. El resultado se expresa en pascales."
                ),
                "expression": "998*9.81*20",
                "difficulty": "INTERMEDIATE",
                "objectives": ["presion-hidrostatica"],
                "excerpts": ["wiki-presion", "wiki-arquimedes"],
            },
        ],
        "derivations": [
            {
                "name": "Ecuación fundamental de la hidrostática",
                "equation": r"\(p = p_0 + \rho\, g\, h\)",
                "equation_id": "eq-hidrostatica",
                "assumptions": ["fluido en reposo", "densidad uniforme", "gravedad constante"],
                "governing_principles": ["equilibrio de fuerzas sobre un elemento de fluido"],
                "steps": [
                    "plantear el equilibrio de un prisma elemental de fluido",
                    "igualar la variación de presión al peso de la columna",
                    "integrar entre la superficie libre y la profundidad h",
                ],
                "variables": {
                    "p": "presión a la profundidad h (Pa)",
                    "p0": "presión en la superficie libre (Pa)",
                    "rho": "densidad del fluido (kg/m^3)",
                    "g": "aceleración de la gravedad (m/s^2)",
                    "h": "profundidad bajo la superficie (m)",
                },
                "limitations": ["densidad variable exige integrar por capas", "no incluye efectos de tensión superficial"],
                "check": {
                    "symbolic": {"equation_left": "p", "equation_right": "p0 + rho*g*h", "solution": {"p": "p0 + rho*g*h"}},
                    "numeric": {"expression": "rho*g*h", "values": {"rho": 998, "g": 9.81, "h": 10}, "claimed": 97903.8},
                    "dimensions": {
                        "expression": "rho*g*h",
                        "symbol_units": {"rho": "kg/m^3", "g": "m/s^2", "h": "m"},
                        "expected_unit": "kg/(m*s^2)",
                    },
                },
            },
        ],
        "notation": [
            {"symbol": "p", "meaning": "presión estática", "units": "Pa"},
            {"symbol": "p0", "meaning": "presión en la superficie libre", "units": "Pa"},
            {"symbol": "h", "meaning": "profundidad bajo la superficie", "units": "m"},
        ],
        "terminology": [
            {"term": "presión hidrostática", "definition": "presión que ejerce un fluido en reposo por efecto de su propio peso."},
            {"term": "empuje de Arquímedes", "definition": "fuerza vertical ascendente igual al peso del fluido desalojado."},
        ],
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
        "worked": {
            "prompt": (
                "Caudal volumétrico por una tubería. Si la sección tiene un área de 0,01 m² y el "
                "fluido circula a 2 m/s, calcula el caudal, igual al producto del área por la "
                "velocidad, con la expresión 0.01*2. El resultado se expresa en metros cúbicos por "
                "segundo."
            ),
            "expression": "0.01*2",
            "excerpts": ["wiki-continuidad", "mit-ocw"],
        },
        "practice": [
            {
                "prompt": (
                    "Velocidad en un estrechamiento. El mismo caudal de 0,02 m³/s atraviesa ahora "
                    "una sección de 0,005 m². Calcula la velocidad, igual al caudal dividido por el "
                    "área, con la expresión 0.02/0.005. El resultado se expresa en metros por "
                    "segundo."
                ),
                "expression": "0.02/0.005",
                "difficulty": "INTERMEDIATE",
                "objectives": ["conservacion-masa", "caudal-volumetrico"],
                "excerpts": ["wiki-continuidad", "mit-ocw"],
            },
        ],
        "derivations": [
            {
                "name": "Conservación de la masa en un tubo de corriente",
                "equation": r"\(A_1 V_1 = A_2 V_2\)",
                "equation_id": "eq-continuidad",
                "assumptions": ["flujo estacionario", "fluido incompresible", "sin fuentes ni sumideros"],
                "governing_principles": ["conservación de la masa"],
                "steps": [
                    "igualar la masa que entra y la que sale del tubo de corriente",
                    "cancelar el intervalo de tiempo",
                    "escribir el caudal como producto del área por la velocidad",
                ],
                "variables": {
                    "A1": "área de la sección de entrada (m^2)",
                    "V1": "velocidad en la entrada (m/s)",
                    "A2": "área de la sección de salida (m^2)",
                    "V2": "velocidad en la salida (m/s)",
                },
                "limitations": ["flujo compresible exige el caudal másico", "régimen no permanente cambia el volumen almacenado"],
                "check": {
                    "symbolic": {"equation_left": "A1*V1", "equation_right": "A2*V2", "solution": {"A2": "A1*V1/V2"}},
                    "dimensions": {
                        "expression": "A1*V1",
                        "symbol_units": {"A1": "m^2", "V1": "m/s"},
                        "expected_unit": "m^3/s",
                    },
                },
            },
        ],
        "notation": [
            {"symbol": "Q", "meaning": "caudal volumétrico", "units": "m^3/s"},
            {"symbol": "A", "meaning": "área de la sección recta", "units": "m^2"},
        ],
        "terminology": [
            {"term": "caudal volumétrico", "definition": "volumen de fluido que atraviesa una sección por unidad de tiempo."},
        ],
    },
    "bernoulli": {
        "excerpts": ["nasa-bern", "wiki-bernoulli", "libretexts-bern"],
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
        "worked": {
            "prompt": (
                "Ley de Torricelli para un orificio de salida. Si un depósito tiene un orificio a "
                "una profundidad de 5 m por debajo de la superficie libre y la gravedad vale "
                "9,81 m/s², calcula la energía cinética por unidad de masa, igual a dos por g por h, "
                "con la expresión 2*9.81*5. El resultado se expresa en metros cuadrados por segundo "
                "cuadrado."
            ),
            "expression": "2*9.81*5",
            "excerpts": ["nasa-bern", "wiki-bernoulli"],
        },
        "practice": [
            {
                "prompt": (
                    "Torricelli con mayor altura. Repite el cálculo de la energía cinética por "
                    "unidad de masa para una profundidad de 10 m con la expresión 2*9.81*10. El "
                    "resultado se expresa en metros cuadrados por segundo cuadrado."
                ),
                "expression": "2*9.81*10",
                "difficulty": "INTERMEDIATE",
                "objectives": ["ley-torricelli"],
                "excerpts": ["nasa-bern", "wiki-bernoulli"],
            },
        ],
        "derivations": [
            {
                "name": "Ley de Torricelli a partir de la ecuación de Bernoulli",
                "equation": r"\(V = \sqrt{2 g h}\)",
                "equation_id": "eq-torricelli",
                "assumptions": ["depósito abierto a la atmósfera", "fluido ideal sin viscosidad", "régimen estacionario"],
                "governing_principles": ["ecuación de Bernoulli", "conservación de la energía mecánica"],
                "steps": [
                    "aplicar Bernoulli entre la superficie libre y el orificio",
                    "igualar la presión en ambos puntos a la presión atmosférica",
                    "despejar la velocidad de salida",
                ],
                "variables": {
                    "V": "velocidad de salida (m/s)",
                    "g": "aceleración de la gravedad (m/s^2)",
                    "h": "altura del líquido sobre el orificio (m)",
                },
                "limitations": ["no incluye pérdidas viscosas", "válido para orificios pequeños frente a la sección del depósito"],
                "check": {
                    "symbolic": {"equation_left": "V^2", "equation_right": "2*g*h", "solution": {"V": "sqrt(2*g*h)"}},
                    "numeric": {"expression": "sqrt(2*g*h)", "values": {"g": 9.81, "h": 4.905}, "claimed": 9.81},
                    "dimensions": {
                        "expression": "sqrt(g*h)",
                        "symbol_units": {"g": "m/s^2", "h": "m"},
                        "expected_unit": "m/s",
                    },
                },
            },
        ],
        "notation": [
            {"symbol": "pt", "meaning": "presión total o de estancamiento", "units": "Pa"},
            {"symbol": "z", "meaning": "altura geodésica sobre el plano de referencia", "units": "m"},
        ],
        "terminology": [
            {"term": "presión de estancamiento", "definition": "presión que alcanza el fluido cuando su velocidad se reduce a cero de forma isoentrópica."},
        ],
    },
    "momentum": {
        "excerpts": ["wiki-rtt", "mit-ocw", "wiki-navier-stokes"],
        "paragraphs": [
            (
                "El teorema del transporte de Reynolds relaciona la variación de una magnitud "
                "extensiva asociada a un sistema material con las variaciones que esa misma magnitud "
                "experimenta dentro de un volumen de control fijo y con el flujo que la atraviesa "
                "por su superficie. Es el puente entre la descripción lagrangiana, que sigue a las "
                "partículas de fluido, y la descripción euleriana, que observa lo que ocurre en "
                "puntos fijos del espacio. Gracias a él, las leyes de conservación de la masa, la "
                "cantidad de movimiento y la energía pueden escribirse directamente sobre un volumen "
                "de control."
            ),
            (
                "A partir del teorema de transporte se obtiene la ecuación de la cantidad de "
                "movimiento para un volumen de control: la fuerza neta que actúa sobre el fluido "
                "contenido en el volumen, incluida la que ejercen las paredes, es igual a la suma de "
                "la variación temporal de la cantidad de movimiento almacenada y del flujo neto de "
                "cantidad de movimiento que cruza la superficie. Esta forma de la ecuación permite "
                "calcular empujes y fuerzas sobre codos y álabes sin conocer el detalle del campo de "
                "velocidades en el interior. Los teoremas de volumen de control son una herramienta "
                "habitual en los cursos avanzados de la disciplina."
            ),
        ],
        "worked": {
            "prompt": (
                "Fuerza sobre un codo. El agua, con densidad 998 kg/m³, entra en un codo por una "
                "sección de 0,01 m² a 2 m/s y sale con un cambio de velocidad de 2 m/s en la "
                "dirección de entrada. Calcula el flujo de cantidad de movimiento con la expresión "
                "998*0.01*2*2. El resultado se expresa en newtons."
            ),
            "expression": "998*0.01*2*2",
            "excerpts": ["wiki-rtt", "mit-ocw"],
        },
        "practice": [
            {
                "prompt": (
                    "Fuerza con cambio de velocidad mayor. Repite el cálculo para un cambio de "
                    "velocidad de 3 m/s con la expresión 998*0.01*2*3. El resultado se expresa en "
                    "newtons."
                ),
                "expression": "998*0.01*2*3",
                "difficulty": "ADVANCED",
                "objectives": ["cantidad-movimiento"],
                "excerpts": ["wiki-rtt", "mit-ocw"],
            },
        ],
        "derivations": [
            {
                "name": "Teorema del transporte de Reynolds",
                "equation": (
                    r"\(\frac{d}{dt}\int_{V} \rho\,dV = \int_{V} \frac{\partial \rho}{\partial t}\,dV"
                    r" + \oint_{S} \rho \vec{V}\cdot d\vec{S}\)"
                ),
                "equation_id": "eq-rtt",
                "assumptions": ["volumen de control fijo en el espacio", "campos derivables"],
                "governing_principles": ["teorema de Leibniz para integrales", "teorema de la divergencia"],
                "steps": [
                    "partir de la derivada temporal de la integral sobre un sistema material",
                    "separar la variación en el interior del volumen de control",
                    "convertir el flujo superficial en una integral sobre la superficie del volumen",
                ],
                "variables": {
                    "rho": "densidad del fluido (kg/m^3)",
                    "V": "velocidad del fluido (m/s)",
                },
                "limitations": ["la demostración rigurosa exige campos derivables", "los choques introducen discontinuidades"],
                "check": {
                    "dimensions": {
                        "expression": "rho*V",
                        "symbol_units": {"rho": "kg/m^3", "V": "m/s"},
                        "expected_unit": "kg/(m^2*s)",
                    },
                },
            },
        ],
        "notation": [
            {"symbol": "F", "meaning": "fuerza resultante sobre el volumen de control", "units": "N"},
            {"symbol": "V", "meaning": "velocidad del fluido", "units": "m/s"},
        ],
        "terminology": [
            {"term": "volumen de control", "definition": "región fija del espacio a través de la cual se estudia el flujo de fluido."},
        ],
    },
    "reynolds": {
        "excerpts": ["nasa-reynolds", "wiki-reynolds", "nasa-boundary"],
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
        "worked": {
            "prompt": (
                "Número de Reynolds del agua en una tubería. Para agua a 20 °C que circula a 2 m/s "
                "por una tubería de 0,1 m de diámetro, con densidad 998 kg/m³ y viscosidad dinámica "
                "0,001 Pa·s, calcula el producto de la densidad, la velocidad y el diámetro dividido "
                "por la viscosidad con la expresión 998*2*0.1/0.001. El resultado es un número "
                "adimensional."
            ),
            "expression": "998*2*0.1/0.001",
            "excerpts": ["nasa-reynolds", "wiki-reynolds"],
        },
        "practice": [
            {
                "prompt": (
                    "Número de Reynolds del aire. Para aire con densidad 1,225 kg/m³ que circula a "
                    "50 m/s por un conducto de 1 m de diámetro y viscosidad dinámica 0,0000181 Pa·s, "
                    "calcula el número de Reynolds con la expresión 1.225*50*1/0.0000181."
                ),
                "expression": "1.225*50*1/0.0000181",
                "difficulty": "ADVANCED",
                "objectives": ["numero-reynolds", "similitud"],
                "excerpts": ["nasa-reynolds", "wiki-reynolds"],
            },
        ],
        "derivations": [
            {
                "name": "Número de Reynolds como parámetro adimensional",
                "equation": r"\(Re = \frac{\rho V D}{\mu}\)",
                "equation_id": "eq-reynolds",
                "assumptions": ["viscosidad constante", "longitud característica D"],
                "governing_principles": ["análisis dimensional"],
                "steps": [
                    "comparar el término de inercia con el término viscoso",
                    "agrupar las magnitudes en un cociente",
                    "comprobar que el cociente es adimensional",
                ],
                "variables": {
                    "Re": "número de Reynolds (adimensional)",
                    "rho": "densidad del fluido (kg/m^3)",
                    "V": "velocidad característica (m/s)",
                    "D": "longitud característica (m)",
                    "mu": "viscosidad dinámica (kg/(m*s))",
                },
                "limitations": ["la elección de la longitud característica depende del problema"],
                "check": {
                    "symbolic": {"equation_left": "Re*mu", "equation_right": "rho*V*D", "solution": {"Re": "rho*V*D/mu"}},
                    "dimensions": {
                        "expression": "rho*V*D/mu",
                        "symbol_units": {"rho": "kg/m^3", "V": "m/s", "D": "m", "mu": "kg/(m*s)"},
                        "expected_unit": "dimensionless",
                    },
                },
            },
        ],
        "notation": [
            {"symbol": "Re", "meaning": "número de Reynolds", "units": "adimensional"},
            {"symbol": "D", "meaning": "longitud característica", "units": "m"},
        ],
        "terminology": [
            {"term": "similitud dinámica", "definition": "correspondencia entre dos flujos con el mismo número de Reynolds."},
            {"term": "régimen laminar", "definition": "flujo ordenado en capas paralelas sin mezcla macroscópica."},
            {"term": "régimen turbulento", "definition": "flujo caótico con remolinos y fluctuaciones de velocidad."},
        ],
    },
    "tuberias": {
        "excerpts": ["wiki-laminar", "wiki-poiseuille", "wiki-turbulento"],
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
                "La ley de Poiseuille determina el caudal de un líquido incompresible y "
                "uniformemente viscoso que fluye en régimen laminar por un tubo cilíndrico de "
                "sección circular constante; el caudal crece con la cuarta potencia del radio y con "
                "la caída de presión, y disminuye al aumentar la viscosidad o la longitud del tubo. "
                "Cuando el número de Reynolds aumenta, el flujo pierde estabilidad y aparecen "
                "remolinos aperiódicos que caracterizan el régimen turbulento. La experiencia "
                "acumulada sitúa la transición en conductos circulares en valores del parámetro "
                "próximos a 2300 y 4000, con una zona intermedia de comportamiento incierto."
            ),
        ],
        "worked": {
            "prompt": (
                "Velocidad media en una tubería. Si un caudal de 0,02 m³/s circula por una tubería "
                "de sección 0,01 m², calcula la velocidad media, igual al caudal dividido por el "
                "área, con la expresión 0.02/0.01. El resultado se expresa en metros por segundo."
            ),
            "expression": "0.02/0.01",
            "excerpts": ["wiki-laminar", "wiki-poiseuille"],
        },
        "practice": [
            {
                "prompt": (
                    "Velocidad media con otro caudal. Repite el cálculo para un caudal de 0,03 m³/s "
                    "y la misma sección de 0,01 m² con la expresión 0.03/0.01. El resultado se "
                    "expresa en metros por segundo."
                ),
                "expression": "0.03/0.01",
                "difficulty": "FOUNDATIONAL",
                "objectives": ["flujo-laminar"],
                "excerpts": ["wiki-laminar", "wiki-turbulento"],
            },
        ],
        "derivations": [
            {
                "name": "Ley de Poiseuille para el flujo laminar en un tubo",
                "equation": r"\(Q = \frac{\pi\,\Delta p\, r^{4}}{8\,\mu\,L}\)",
                "equation_id": "eq-poiseuille",
                "assumptions": ["flujo laminar estacionario", "fluido incompresible", "tubo horizontal de sección constante"],
                "governing_principles": ["equilibrio entre presión y viscosidad", "condición de no deslizamiento en la pared"],
                "steps": [
                    "equilibrar la fuerza de presión con la fuerza viscosa sobre un cilindro de fluido",
                    "integrar el perfil de velocidades parabólico",
                    "integrar el perfil sobre la sección para obtener el caudal",
                ],
                "variables": {
                    "Q": "caudal volumétrico (m^3/s)",
                    "dp": "caída de presión a lo largo del tubo (Pa)",
                    "r": "radio interior del tubo (m)",
                    "mu": "viscosidad dinámica (kg/(m*s))",
                    "L": "longitud del tubo (m)",
                },
                "limitations": ["no válido en régimen turbulento", "supone tubo horizontal sin accidentes"],
                "check": {
                    "symbolic": {"equation_left": "Q*8*mu*L", "equation_right": "pi*dp*r^4", "solution": {"Q": "pi*dp*r^4/(8*mu*L)"}},
                    "dimensions": {
                        "expression": "dp*r**4/(mu*L)",
                        "symbol_units": {"dp": "kg/(m*s^2)", "r": "m", "mu": "kg/(m*s)", "L": "m"},
                        "expected_unit": "m^3/s",
                    },
                },
            },
        ],
        "notation": [
            {"symbol": "Δp", "meaning": "caída de presión a lo largo del tubo", "units": "Pa"},
            {"symbol": "r", "meaning": "radio interior del conducto", "units": "m"},
            {"symbol": "L", "meaning": "longitud del conducto", "units": "m"},
        ],
        "terminology": [
            {"term": "flujo de Poiseuille", "definition": "flujo laminar estacionario de un fluido viscoso en un tubo cilíndrico."},
        ],
    },
    "capa-limite": {
        "excerpts": ["nasa-boundary", "wiki-capa-limite", "mit-ocw"],
        "paragraphs": [
            (
                "Junto a la superficie de un cuerpo que se mueve en un fluido se forma una capa "
                "delgada en la que la velocidad pasa de cero, en la pared, al valor de la corriente "
                "libre, fuera de ella. La NASA explica que las moléculas adheridas a la superficie "
                "frenan por colisiones a las capas inmediatamente superiores, de modo que el espesor "
                "característico de esa capa límite depende del número de Reynolds. La versión "
                "española de Wikipedia define la capa límite como la zona perturbada por la "
                "presencia de un sólido por efecto de la viscosidad y la tensión cortante. La "
                "teoría que describe estos efectos fue presentada por Ludwig Prandtl a comienzos "
                "del siglo XX."
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
        "worked": {
            "prompt": (
                "Espesor de desplazamiento de una capa límite de perfil lineal. Sobre una placa "
                "plana se desarrolla una capa límite de 0,02 m de espesor con un perfil de "
                "velocidades lineal, para el que el espesor de desplazamiento vale la mitad del "
                "espesor de la capa. Calcula ese espesor con la expresión 0.02/2. El resultado se "
                "expresa en metros."
            ),
            "expression": "0.02/2",
            "excerpts": ["nasa-boundary", "wiki-capa-limite"],
        },
        "practice": [
            {
                "prompt": (
                    "Espesor de desplazamiento de un perfil parabólico. Para una capa límite de "
                    "0,06 m de espesor cuyo perfil de velocidades es parabólico, el espesor de "
                    "desplazamiento vale un tercio del espesor de la capa. Calcula ese espesor con "
                    "la expresión 0.06/3. El resultado se expresa en metros."
                ),
                "expression": "0.06/3",
                "difficulty": "ADVANCED",
                "objectives": ["espesor-desplazamiento"],
                "excerpts": ["nasa-boundary", "wiki-capa-limite"],
            },
        ],
        "derivations": [
            {
                "name": "Espesor de desplazamiento de la capa límite",
                "equation": r"\(\delta^{*} = \int_{0}^{\infty}\left(1 - \frac{V}{U}\right) dy\)",
                "equation_id": "eq-espesor-desplazamiento",
                "assumptions": ["perfil de velocidades conocido", "corriente libre uniforme U"],
                "governing_principles": ["déficit de caudal respecto al flujo ideal"],
                "steps": [
                    "comparar el caudal real con el caudal ideal en la capa",
                    "definir el espesor equivalente del déficit",
                    "integrar el déficit a lo largo de la normal a la pared",
                ],
                "variables": {
                    "delta": "espesor de la capa límite (m)",
                    "V": "velocidad local dentro de la capa (m/s)",
                    "U": "velocidad de la corriente libre (m/s)",
                    "y": "distancia normal a la pared (m)",
                },
                "limitations": ["requiere conocer el perfil de velocidades", "no describe la zona separada"],
                "check": {
                    "dimensions": {
                        "expression": "1 - V/U",
                        "symbol_units": {"V": "m/s", "U": "m/s"},
                        "expected_unit": "dimensionless",
                    },
                },
            },
        ],
        "notation": [
            {"symbol": "δ", "meaning": "espesor de la capa límite", "units": "m"},
            {"symbol": "δ*", "meaning": "espesor de desplazamiento", "units": "m"},
        ],
        "terminology": [
            {"term": "capa límite", "definition": "región próxima a un sólido donde la viscosidad modifica el campo de velocidades."},
        ],
    },
    "instrumentacion": {
        "excerpts": ["wiki-pitot", "wiki-manometro", "nasa-bern"],
        "paragraphs": [
            (
                "El tubo de Pitot mide la presión total o de estancamiento del flujo: la toma "
                "frontal se orienta de cara a la corriente y frena el fluido en su entrada, de modo "
                "que registra la suma de la presión estática y de la presión dinámica. Combinando esa "
                "lectura con la presión estática medida en una toma lateral, la ecuación de Bernoulli "
                "permite despejar la velocidad del flujo. Por ello el tubo de Pitot es el elemento "
                "central del velocímetro aerodinámico de las aeronaves."
            ),
            (
                "Los manómetros son instrumentos que miden la presión de los fluidos contenidos en "
                "recipientes cerrados y se fabrican en versiones para líquidos y para gases. El "
                "manómetro en U compara la presión de un fluido con una columna de líquido de "
                "referencia y su lectura es proporcional a la diferencia de alturas. Estos "
                "instrumentos, junto con el tubo de Pitot, se emplean para verificar de forma directa "
                "las predicciones de la estática y de la dinámica de fluidos."
            ),
        ],
        "worked": {
            "prompt": (
                "Presión dinámica del aire. Para aire con densidad 1,225 kg/m³ que circula a "
                "10 m/s, calcula la presión dinámica, igual a la mitad del producto de la densidad "
                "por el cuadrado de la velocidad, con la expresión 0.5*1.225*100. El resultado se "
                "expresa en pascales."
            ),
            "expression": "0.5*1.225*100",
            "excerpts": ["wiki-pitot", "wiki-manometro"],
        },
        "practice": [
            {
                "prompt": (
                    "Presión dinámica a mayor velocidad. Repite el cálculo para una velocidad de "
                    "20 m/s con la expresión 0.5*1.225*400. El resultado se expresa en pascales."
                ),
                "expression": "0.5*1.225*400",
                "difficulty": "INTERMEDIATE",
                "objectives": ["tubo-pitot"],
                "excerpts": ["wiki-pitot", "nasa-bern"],
            },
        ],
        "derivations": [
            {
                "name": "Velocidad a partir de la presión de estancamiento",
                "equation": r"\(V = \sqrt{\frac{2\,(p_t - p_s)}{\rho}}\)",
                "equation_id": "eq-pitot",
                "assumptions": ["flujo incompresible", "medición isoentrópica en el punto de remanso"],
                "governing_principles": ["ecuación de Bernoulli aplicada al punto de estancamiento"],
                "steps": [
                    "aplicar Bernoulli entre la corriente libre y el punto de remanso",
                    "igualar la velocidad en el punto de remanso a cero",
                    "despejar la velocidad de la corriente libre",
                ],
                "variables": {
                    "V": "velocidad de la corriente libre (m/s)",
                    "pt": "presión total o de estancamiento (Pa)",
                    "ps": "presión estática (Pa)",
                    "rho": "densidad del fluido (kg/m^3)",
                },
                "limitations": ["no válido en flujo compresible a alta velocidad", "sensible a la alineación de la sonda"],
                "check": {
                    "symbolic": {
                        "equation_left": "V^2",
                        "equation_right": "2*(pt-ps)/rho",
                        "solution": {"V": "sqrt(2*(pt-ps)/rho)"},
                    },
                    "dimensions": {
                        "expression": "sqrt(p/rho)",
                        "symbol_units": {"p": "kg/(m*s^2)", "rho": "kg/m^3"},
                        "expected_unit": "m/s",
                    },
                },
            },
        ],
        "notation": [
            {"symbol": "ps", "meaning": "presión estática medida en la corriente", "units": "Pa"},
            {"symbol": "q", "meaning": "presión dinámica del flujo", "units": "Pa"},
        ],
        "terminology": [
            {"term": "manómetro", "definition": "instrumento que mide la presión de un fluido contenido en un recipiente cerrado."},
        ],
    },
}


# Additional pedagogical prose for each chapter: a definition paragraph, a
# self-check paragraph and one more explanatory paragraph. All of it is
# original Spanish prose supported by the same retrieved sources.
EXTRA_PROSE: dict[str, dict[str, object]] = {
    "introduccion": {
        "definition": (
            "Un fluido es un medio continuo que se deforma de manera continua bajo la acción de un "
            "esfuerzo cortante, por pequeño que este sea, y que no recupera su forma original cuando "
            "cesa la solicitación. Esta definición diferencia a los fluidos de los sólidos elásticos, "
            "que se deforman de forma limitada y recuperan su forma cuando desaparece la carga."
        ),
        "self_check": (
            "Comprueba tu comprensión: ¿por qué la hipótesis del medio continuo permite hablar de la "
            "densidad en un punto si el fluido está formado por moléculas? Explica también qué "
            "diferencia fundamental separa a un fluido de un sólido elástico frente a un esfuerzo "
            "cortante."
        ),
        "extra": [
            (
                "El estudio se organiza en tres bloques. El primero cubre la estática, en la que el "
                "fluido está en reposo y solo aparecen tensiones normales; el segundo trata la dinámica "
                "del flujo ideal mediante la ecuación de continuidad, la ecuación de Bernoulli y los "
                "teoremas de volumen de control; y el tercero aborda el flujo real, en el que la "
                "viscosidad, la capa límite y la instrumentación de medida determinan el "
                "comportamiento del fluido. Este recorrido coincide con la secuencia del curso "
                "avanzado de mecánica de fluidos del MIT y con el orden habitual de la asignatura en "
                "el plan de estudios de la Universidad de León."
            ),
        ],
    },
    "propiedades": {
        "definition": (
            "La densidad de un fluido es la masa por unidad de volumen y su peso específico es el "
            "producto de la densidad por la aceleración de la gravedad. La viscosidad dinámica es la "
            "constante de proporcionalidad entre la tensión cortante aplicada y el gradiente de "
            "velocidad, y la viscosidad cinemática es el cociente entre la viscosidad dinámica y la "
            "densidad."
        ),
        "self_check": (
            "Comprueba tu comprensión: si un líquido y un gas tuvieran la misma viscosidad dinámica, "
            "¿cuál de los dos presentaría una viscosidad cinemática mayor y por qué? Justifica la "
            "respuesta a partir de la definición de viscosidad cinemática."
        ),
        "extra": [
            (
                "Además de la densidad y la viscosidad, en el flujo aparecen otras propiedades de "
                "interés práctico. La compresibilidad mide cómo cambia el volumen de un fluido cuando "
                "varía la presión y permite clasificar los flujos como incompresibles o compresibles "
                "según la magnitud de esa variación; en los líquidos es tan pequeña que suele "
                "despreciarse, mientras que en los gases a alta velocidad no puede ignorarse. La "
                "tensión superficial, propia de la interfaz entre un líquido y un gas, explica la "
                "formación de gotas y los efectos capilares, y la presión de vapor marca la frontera a "
                "partir de la cual el líquido comienza a hervir, fenómeno relacionado con la cavitación "
                "en bombas y hélices."
            ),
            (
                "Los fluidos se clasifican según su respuesta a la tensión cortante. Los fluidos "
                "newtonianos, como el agua o el aire, presentan una viscosidad constante que no "
                "depende de la velocidad de deformación, mientras que los no newtonianos, como la "
                "sangre, la pintura o el gel, muestran una viscosidad aparente que cambia con el "
                "gradiente de velocidad. Esta distinción es esencial al elegir modelos de flujo y "
                "explica por qué la ley de Poiseuille solo se aplica a fluidos de comportamiento "
                "newtoniano."
            ),
        ],
    },
    "estatica": {
        "definition": (
            "La presión en un punto de un fluido es la fuerza normal por unidad de área que ejerce el "
            "fluido sobre una superficie sumergida, y en un fluido en reposo su valor depende de la "
            "profundidad. El empuje hidrostático es la fuerza vertical ascendente que un fluido en "
            "reposo ejerce sobre un cuerpo sumergido, igual al peso del fluido desalojado."
        ),
        "self_check": (
            "Comprueba tu comprensión: ¿por qué la presión hidrostática en un punto no depende de la "
            "forma del recipiente que contiene el líquido? Explica qué ocurre con el empuje de "
            "Arquímedes cuando un cuerpo flota en equilibrio y cómo se relaciona con su peso."
        ),
        "extra": [
            (
                "La manometría es la aplicación directa de la hidrostática a la medida de presiones. "
                "En un manómetro en U de líquido, la diferencia de presión entre dos puntos se obtiene "
                "a partir de la diferencia de alturas entre las dos ramas y del peso específico del "
                "líquido manométrico, de modo que la lectura es proporcional a la presión que se desea "
                "conocer. La flotabilidad, por su parte, gobierna la estabilidad de los cuerpos "
                "sumergidos: un cuerpo flota cuando el empuje iguala a su peso y lo hace de forma "
                "estable cuando el centro de carena se sitúa en una posición adecuada respecto al "
                "centro de gravedad."
            ),
            (
                "En la práctica conviene distinguir entre presión absoluta y presión manométrica. La "
                "presión absoluta se mide respecto al vacío, mientras que la manométrica se mide "
                "respecto a la presión atmosférica local y es la que registran la mayoría de los "
                "instrumentos. La presión atmosférica disminuye con la altitud siguiendo una ley "
                "aproximadamente exponencial, de modo que los cálculos de aeronáutica emplean una "
                "atmósfera estándar que fija temperatura, presión y densidad de referencia a cada "
                "altitud."
            ),
        ],
    },
    "continuidad": {
        "definition": (
            "La ecuación de continuidad es la expresión matemática de la conservación de la masa "
            "aplicada a un fluido: el caudal másico que entra en un volumen de control menos el que "
            "sale es igual a la variación de la masa almacenada. Para un fluido incompresible en "
            "régimen permanente, el caudal volumétrico es el mismo en todas las secciones de un tubo "
            "de corriente."
        ),
        "self_check": (
            "Comprueba tu comprensión: si en una tubería horizontal se reduce a la mitad el área de "
            "la sección y el caudal permanece constante, ¿cómo cambia la velocidad media? Justifica "
            "el resultado a partir de la conservación de la masa."
        ),
        "extra": [
            (
                "En forma diferencial la ecuación de continuidad relaciona la variación local de la "
                "densidad con la divergencia del vector flujo másico. Si el fluido es incompresible la "
                "densidad es constante y la ecuación se reduce a la anulación de la divergencia de la "
                "velocidad, condición que expresa que el fluido no puede acumularse en ningún punto. "
                "En régimen permanente el campo de velocidades no cambia con el tiempo, pero puede "
                "variar de unas partículas a otras a lo largo de sus trayectorias, de modo que la "
                "restricción de continuidad sigue siendo necesaria para describir correctamente el "
                "flujo."
            ),
            (
                "La continuidad explica el comportamiento de boquillas, difusores y medidores de "
                "caudal. Cuando el fluido atraviesa una boquilla, la reducción de área obliga a "
                "aumentar la velocidad para conservar el caudal, y al atravesar un difusor ocurre lo "
                "contrario: el área crece y la velocidad disminuye. Este mismo razonamiento permite "
                "relacionar las velocidades en dos secciones cualesquiera de un tubo de Venturi y, "
                "junto con la ecuación de Bernoulli, obtener el caudal a partir de la caída de "
                "presión medida."
            ),
        ],
    },
    "bernoulli": {
        "definition": (
            "La ecuación de Bernoulli es la expresión de la conservación de la energía mecánica por "
            "unidad de volumen en un fluido ideal en movimiento, y establece que la suma de la presión "
            "estática y de la presión dinámica permanece constante a lo largo de una línea de "
            "corriente. La ley de Torricelli es el caso particular que da la velocidad de salida de un "
            "líquido por un orificio en función de la altura del líquido sobre él."
        ),
        "self_check": (
            "Comprueba tu comprensión: ¿por qué la presión estática disminuye cuando el fluido acelera "
            "en un estrechamiento si la energía mecánica total permanece constante? Explica qué "
            "hipótesis del fluido ideal deben cumplirse para poder aplicar la ecuación de Bernoulli."
        ),
        "extra": [
            (
                "La utilidad de la ecuación de Bernoulli se aprecia en numerosos dispositivos y "
                "fenómenos. El tubo de Venturi mide el caudal a partir de la caída de presión que "
                "acompaña al estrechamiento, el tubo de Pitot mide la velocidad comparando la presión "
                "total con la estática y el efecto Magnus explica la trayectoria curva de un balón en "
                "rotación. En todos estos casos el modelo ideal proporciona resultados fiables mientras "
                "las pérdidas viscosas sean pequeñas frente a los términos de presión y de energía "
                "cinética; cuando no lo son, la ecuación debe corregirse con un término de pérdida de "
                "carga."
            ),
        ],
    },
    "momentum": {
        "definition": (
            "El teorema del transporte de Reynolds es la relación que convierte la derivada de una "
            "magnitud extensiva de un sistema material en la suma de su variación dentro de un volumen "
            "de control fijo y del flujo que la atraviesa por su superficie. La ecuación de la "
            "cantidad de movimiento es la aplicación de ese teorema al momento lineal y permite "
            "relacionar la fuerza neta sobre el fluido con el cambio de cantidad de movimiento."
        ),
        "self_check": (
            "Comprueba tu comprensión: ¿qué ventaja aporta analizar un problema con un volumen de "
            "control en lugar de seguir a las partículas del fluido? Explica cómo se calcula la fuerza "
            "que el fluido ejerce sobre un codo a partir del cambio de cantidad de movimiento."
        ),
        "extra": [
            (
                "El teorema de transporte tiene una lectura física inmediata: lo que cambia dentro de "
                "una región fija del espacio se debe tanto a las variaciones locales de las "
                "propiedades como al hecho de que el fluido entra y sale a través de su frontera. Esta "
                "doble contribución es la que permite formular las leyes de conservación en la "
                "descripción euleriana, más cómoda para resolver problemas prácticos que la "
                "descripción lagrangiana. A partir de la misma herramienta se obtienen también la "
                "ecuación de la energía y el momento angular, de gran utilidad en el análisis de "
                "turbomáquinas y de vehículos."
            ),
        ],
    },
    "reynolds": {
        "definition": (
            "El número de Reynolds es un parámetro adimensional que compara las fuerzas de inercia "
            "con las fuerzas viscosas de un flujo mediante el cociente entre el producto de la "
            "densidad, la velocidad y una longitud característica y la viscosidad dinámica. La "
            "similitud dinámica es la condición que permite reproducir a escala un flujo real "
            "exigiendo que el modelo y el prototipo compartan el mismo número de Reynolds."
        ),
        "self_check": (
            "Comprueba tu comprensión: ¿por qué al aumentar la velocidad de un flujo el número de "
            "Reynolds crece y el régimen tiende a volverse turbulento? Explica para qué sirve mantener "
            "el mismo número de Reynolds en un ensayo en túnel de viento."
        ),
        "extra": [
            (
                "El número de Reynolds es la herramienta básica del análisis dimensional en mecánica "
                "de fluidos. Los teoremas de similitud permiten reducir un problema con muchas "
                "variables a un número reducido de grupos adimensionales, entre ellos el de Reynolds, "
                "el de Mach y el de Froude, cada uno asociado a un efecto físico dominante. En el caso "
                "de un conducto circular, la experiencia sitúa la transición del régimen laminar al "
                "turbulento en valores comprendidos entre 2300 y 4000, con una zona intermedia en la "
                "que el comportamiento es incierto y depende de las perturbaciones presentes en la "
                "instalación."
            ),
            (
                "Junto al número de Reynolds aparecen otros grupos adimensionales que caracterizan "
                "efectos físicos distintos. El número de Mach compara la velocidad del flujo con la "
                "velocidad del sonido y decide si el flujo debe tratarse como compresible; el número "
                "de Froude relaciona las fuerzas de inercia con las gravitatorias y es clave en el "
                "flujo con superficie libre; y el número de Prandtl o el de Nusselt aparecen cuando el "
                "problema combina el movimiento con la transferencia de calor."
            ),
        ],
    },
    "tuberias": {
        "definition": (
            "El régimen laminar es el movimiento ordenado de un fluido en capas paralelas que no se "
            "entremezclan, y en un tubo circular da lugar a un perfil de velocidades parabólico con "
            "velocidad nula en la pared. La ley de Poiseuille es la expresión del caudal de un líquido "
            "viscoso que circula en régimen laminar por un tubo cilíndrico de sección constante."
        ),
        "self_check": (
            "Comprueba tu comprensión: ¿por qué la ley de Poiseuille deja de ser válida cuando el "
            "flujo se vuelve turbulento? Explica cómo cambia el caudal si se duplica el radio del tubo "
            "manteniendo constantes la caída de presión, la viscosidad y la longitud."
        ),
        "extra": [
            (
                "Para calcular la pérdida de carga en instalaciones reales se emplea el factor de "
                "fricción, que en régimen laminar depende solo del número de Reynolds y en régimen "
                "turbulento también de la rugosidad relativa del conducto. En el caso laminar ese "
                "factor vale exactamente el cociente entre 64 y el número de Reynolds, resultado que "
                "se obtiene directamente de la ley de Poiseuille. Los diagramas de Moody recogen de "
                "forma gráfica la dependencia del factor de fricción con ambos parámetros y son la "
                "herramienta habitual para dimensionar tuberías y estimar la potencia de bombeo "
                "necesaria."
            ),
            (
                "En régimen turbulento el campo de velocidades pierde su forma parabólica y aparecen "
                "fluctuaciones que incrementan notablemente la pérdida de energía. La pérdida de carga "
                "se calcula entonces con el factor de fricción y con el término cinético, y a ella se "
                "añaden las pérdidas locales que producen codos, válvulas y ensanchamientos. En las "
                "instalaciones reales estos elementos se contabilizan mediante una longitud equivalente "
                "o un coeficiente de pérdida que se suma a la longitud recta de la conducción."
            ),
        ],
    },
    "capa-limite": {
        "definition": (
            "La capa límite es la región delgada próxima a un sólido en la que la velocidad del "
            "fluido pasa de cero, en la pared, al valor de la corriente libre debido a la acción de la "
            "viscosidad. El espesor de desplazamiento es el espesor ficticio de una capa de fluido "
            "ideal que tendría el mismo déficit de caudal que la capa límite real."
        ),
        "self_check": (
            "Comprueba tu comprensión: ¿por qué la capa límite se engrosa a medida que el fluido "
            "avanza sobre una placa plana? Explica en qué consiste la separación de la capa límite y "
            "qué consecuencia tiene sobre la sustentación de un ala."
        ),
        "extra": [
            (
                "Dentro de la capa límite la tensión cortante en la pared depende del gradiente de "
                "velocidad junto al sólido, de modo que la resistencia por fricción de un cuerpo se "
                "calcula integrando esa tensión sobre su superficie. Cuando el gradiente de presión "
                "adverso es suficientemente intenso, el fluido próximo a la pared pierde cantidad de "
                "movimiento, se detiene y la capa se desprende, formando una estela turbulenta que "
                "aumenta la resistencia de forma y reduce la sustentación. Este fenómeno explica la "
                "entrada en pérdida del ala a ángulos de ataque elevados y obliga a controlar la capa "
                "límite mediante dispositivos como los generadores de vórtices."
            ),
        ],
    },
    "instrumentacion": {
        "definition": (
            "El tubo de Pitot es un instrumento que mide la presión total o de estancamiento mediante "
            "una toma frontal orientada de cara a la corriente, y que junto con la presión estática "
            "permite determinar la velocidad del flujo. El manómetro es un instrumento que mide la "
            "presión de un fluido contenido en un recipiente cerrado comparándola con la de una "
            "columna de líquido de referencia."
        ),
        "self_check": (
            "Comprueba tu comprensión: ¿por qué el tubo de Pitot debe alinearse con la dirección del "
            "flujo para que su lectura sea correcta? Explica cómo se obtiene la velocidad del aire a "
            "partir de la diferencia entre la presión total y la presión estática."
        ),
        "extra": [
            (
                "Además del tubo de Pitot y del manómetro, la instrumentación de fluidos incluye "
                "otros medidores de uso frecuente. Los caudalímetros de placa de orificio y de tobera "
                "miden el caudal a partir de la caída de presión que produce el estrechamiento, los "
                "rotámetros dan una lectura directa proporcional al caudal y los anemómetros de hilo "
                "caliente aprovechan la transferencia de calor para medir velocidades muy bajas con "
                "gran resolución. En todos los casos la calibración periódica y la correcta estimación "
                "de la incertidumbre son imprescindibles para que la medida sea fiable."
            ),
            (
                "Toda medida de laboratorio lleva asociada una incertidumbre que depende del "
                "instrumento y del procedimiento. En la medida de presión con columnas de líquido "
                "influyen la lectura de alturas, la densidad del líquido manométrico y la temperatura, "
                "mientras que en el tubo de Pitot hay que cuidar la alineación con la corriente y la "
                "distancia entre las tomas. La calibración periódica y la estimación de la "
                "incertidumbre combinada son imprescindibles para que el valor medido sea comparable "
                "con las predicciones teóricas."
            ),
        ],
    },
}

# A second practice exercise per chapter, with a difficulty level different from
# the first one, so every chapter records at least two difficulty levels.
EXTRA_PRACTICE: dict[str, list[dict[str, object]]] = {
    "introduccion": [
        {
            "prompt": (
                "Peso de un volumen de aire. Con densidad 1,225 kg/m³ y gravedad 9,81 m/s², calcula "
                "el peso de 2 m³ de aire, igual a la densidad por la gravedad por el volumen, con la "
                "expresión 1.225*9.81*2. El resultado se expresa en newtons."
            ),
            "expression": "1.225*9.81*2",
            "difficulty": "INTERMEDIATE",
            "objectives": ["sistema-unidades"],
            "excerpts": ["ule-plan", "mit-ocw"],
        },
    ],
    "propiedades": [
        {
            "prompt": (
                "Viscosidad dinámica a partir de una tensión cortante. Si sobre un fluido actúa una "
                "tensión cortante de 2 Pa y el gradiente de velocidad vale 500 por segundo, calcula la "
                "viscosidad dinámica, igual al cociente entre ambas magnitudes, con la expresión "
                "2/500. El resultado se expresa en pascales por segundo."
            ),
            "expression": "2/500",
            "difficulty": "ADVANCED",
            "objectives": ["viscosidad-dinamica"],
            "excerpts": ["nasa-viscosity", "wiki-viscosidad"],
        },
    ],
    "estatica": [
        {
            "prompt": (
                "Empuje sobre un cuerpo sumergido. Un cuerpo desaloja 0,02 m³ de agua con densidad "
                "998 kg/m³, bajo una gravedad de 9,81 m/s². Calcula el empuje de Arquímedes, igual al "
                "peso del fluido desalojado, con la expresión 998*9.81*0.02. El resultado se expresa "
                "en newtons."
            ),
            "expression": "998*9.81*0.02",
            "difficulty": "FOUNDATIONAL",
            "objectives": ["flotabilidad"],
            "excerpts": ["wiki-presion", "wiki-arquimedes"],
        },
    ],
    "continuidad": [
        {
            "prompt": (
                "Caudal por una sección mayor. Para un área de 0,03 m² y una velocidad de 4 m/s, "
                "calcula el caudal con la expresión 0.03*4. El resultado se expresa en metros cúbicos "
                "por segundo."
            ),
            "expression": "0.03*4",
            "difficulty": "FOUNDATIONAL",
            "objectives": ["caudal-volumetrico"],
            "excerpts": ["wiki-continuidad", "mit-ocw"],
        },
    ],
    "bernoulli": [
        {
            "prompt": (
                "Torricelli con poca altura. Repite el cálculo de la energía cinética por unidad de "
                "masa para una profundidad de 2 m con la expresión 2*9.81*2. El resultado se expresa "
                "en metros cuadrados por segundo cuadrado."
            ),
            "expression": "2*9.81*2",
            "difficulty": "FOUNDATIONAL",
            "objectives": ["ley-torricelli"],
            "excerpts": ["nasa-bern", "wiki-bernoulli"],
        },
    ],
    "momentum": [
        {
            "prompt": (
                "Fuerza con sección mayor. El agua de densidad 998 kg/m³ circula por una sección de "
                "0,02 m² a 1 m/s y cambia su velocidad en 1 m/s. Calcula el flujo de cantidad de "
                "movimiento con la expresión 998*0.02*1*1. El resultado se expresa en newtons."
            ),
            "expression": "998*0.02*1*1",
            "difficulty": "FOUNDATIONAL",
            "objectives": ["cantidad-movimiento"],
            "excerpts": ["wiki-rtt", "mit-ocw"],
        },
    ],
    "reynolds": [
        {
            "prompt": (
                "Número de Reynolds del agua con menor diámetro. Para agua con densidad 998 kg/m³ que "
                "circula a 1,5 m/s por un tubo de 0,05 m de diámetro y viscosidad dinámica 0,001 Pa·s, "
                "calcula el número de Reynolds con la expresión 998*1.5*0.05/0.001."
            ),
            "expression": "998*1.5*0.05/0.001",
            "difficulty": "INTERMEDIATE",
            "objectives": ["numero-reynolds"],
            "excerpts": ["nasa-reynolds", "wiki-reynolds"],
        },
    ],
    "tuberias": [
        {
            "prompt": (
                "Velocidad media con un caudal mayor. Repite el cálculo para un caudal de 0,06 m³/s "
                "y una sección de 0,01 m² con la expresión 0.06/0.01. El resultado se expresa en "
                "metros por segundo."
            ),
            "expression": "0.06/0.01",
            "difficulty": "INTERMEDIATE",
            "objectives": ["flujo-laminar"],
            "excerpts": ["wiki-laminar", "wiki-poiseuille"],
        },
    ],
    "capa-limite": [
        {
            "prompt": (
                "Espesor de desplazamiento de una capa más gruesa. Para una capa límite de 0,1 m de "
                "espesor con un perfil de velocidades lineal, el espesor de desplazamiento vale la "
                "mitad del espesor. Calcula ese espesor con la expresión 0.1/2. El resultado se "
                "expresa en metros."
            ),
            "expression": "0.1/2",
            "difficulty": "INTERMEDIATE",
            "objectives": ["espesor-desplazamiento"],
            "excerpts": ["nasa-boundary", "wiki-capa-limite"],
        },
    ],
    "instrumentacion": [
        {
            "prompt": (
                "Presión dinámica a baja velocidad. Para aire con densidad 1,225 kg/m³ que circula a "
                "5 m/s, calcula la presión dinámica con la expresión 0.5*1.225*25. El resultado se "
                "expresa en pascales."
            ),
            "expression": "0.5*1.225*25",
            "difficulty": "FOUNDATIONAL",
            "objectives": ["tubo-pitot"],
            "excerpts": ["wiki-pitot", "nasa-bern"],
        },
    ],
}

# Derivations for the two chapters that did not have one yet.
EXTRA_DERIVATIONS: dict[str, list[dict[str, object]]] = {
    "introduccion": [
        {
            "name": "Peso específico de un fluido",
            "equation": r"\(\gamma = \rho\, g\)",
            "equation_id": "eq-peso-especifico",
            "assumptions": ["densidad uniforme", "gravedad constante"],
            "governing_principles": ["segunda ley de Newton aplicada a un volumen unitario"],
            "steps": [
                "multiplicar la densidad por el volumen para obtener la masa",
                "multiplicar la masa por la gravedad para obtener el peso",
                "dividir por el volumen para obtener el peso específico",
            ],
            "variables": {
                "gamma": "peso específico (kg/(m^2*s^2))",
                "rho": "densidad del fluido (kg/m^3)",
                "g": "aceleración de la gravedad (m/s^2)",
            },
            "limitations": ["en campos gravitatorios variables la gravedad deja de ser constante"],
            "check": {
                "symbolic": {"equation_left": "gamma", "equation_right": "rho*g", "solution": {"gamma": "rho*g"}},
                "dimensions": {
                    "expression": "rho*g",
                    "symbol_units": {"rho": "kg/m^3", "g": "m/s^2"},
                    "expected_unit": "kg/(m^2*s^2)",
                },
            },
        },
    ],
    "propiedades": [
        {
            "name": "Viscosidad cinemática como cociente de viscosidad y densidad",
            "equation": r"\(\nu = \frac{\mu}{\rho}\)",
            "equation_id": "eq-viscosidad-cinematica",
            "assumptions": ["fluido newtoniano", "densidad constante"],
            "governing_principles": ["definición de viscosidad cinemática"],
            "steps": [
                "partir de la definición como cociente entre viscosidad dinámica y densidad",
                "comprobar dimensionalmente el cociente",
                "despejar la viscosidad dinámica cuando interese",
            ],
            "variables": {
                "nu": "viscosidad cinemática (m^2/s)",
                "mu": "viscosidad dinámica (kg/(m*s))",
                "rho": "densidad del fluido (kg/m^3)",
            },
            "limitations": ["la definición no presupone comportamiento newtoniano"],
            "check": {
                "symbolic": {"equation_left": "nu*rho", "equation_right": "mu", "solution": {"nu": "mu/rho"}},
                "dimensions": {
                    "expression": "mu/rho",
                    "symbol_units": {"mu": "kg/(m*s)", "rho": "kg/m^3"},
                    "expected_unit": "m^2/s",
                },
            },
        },
    ],
}


# The prompt is the problem statement. It no longer repeats a raw arithmetic
# expression: the arithmetic belongs to the verified record, not to the prose.
WORKED_PROMPTS: dict[str, str] = {
    "introduccion": (
        "Peso específico del aire. En condiciones estándar al nivel del mar la densidad del aire es "
        "1,225 kg/m³ y la aceleración de la gravedad es 9,81 m/s². Calcula el peso específico del aire "
        "y exprésalo en newtons por metro cúbico."
    ),
    "propiedades": (
        "Viscosidad cinemática del agua. El agua a 20 °C tiene una viscosidad dinámica de 0,001 Pa·s y "
        "una densidad de 998 kg/m³. Calcula su viscosidad cinemática y exprésala en metros cuadrados por "
        "segundo."
    ),
    "estatica": (
        "Presión hidrostática a diez metros de profundidad. Con densidad 998 kg/m³, gravedad 9,81 m/s² y "
        "profundidad 10 m, calcula la presión manométrica en el seno del agua y exprésala en pascales."
    ),
    "continuidad": (
        "Caudal volumétrico por una tubería. Por una sección de 0,01 m² circula agua a 2 m/s. Calcula el "
        "caudal volumétrico y exprésalo en metros cúbicos por segundo."
    ),
    "bernoulli": (
        "Ley de Torricelli. Un depósito abierto tiene un orificio de salida 5 m por debajo de la "
        "superficie libre. Con g = 9,81 m/s², calcula la energía cinética específica y, a partir de ella, "
        "la velocidad de salida."
    ),
    "momentum": (
        "Fuerza sobre un codo. El agua de densidad 998 kg/m³ entra en un codo por una sección de 0,01 m² "
        "a 2 m/s y cambia su velocidad en 2 m/s en la dirección de la corriente. Calcula la fuerza que el "
        "fluido ejerce sobre el codo y exprésala en newtons."
    ),
    "reynolds": (
        "Número de Reynolds del agua en una tubería. Para agua a 20 °C (densidad 998 kg/m³, viscosidad "
        "dinámica 0,001 Pa·s) que circula a 2 m/s por una tubería de 0,1 m de diámetro, calcula el número "
        "de Reynolds e interpreta el régimen de flujo."
    ),
    "tuberias": (
        "Velocidad media en una tubería. Por una tubería de sección 0,01 m² circula un caudal de "
        "0,02 m³/s. Calcula la velocidad media y exprésala en metros por segundo."
    ),
    "capa-limite": (
        "Espesor de desplazamiento de una capa límite de perfil lineal. Sobre una placa plana se "
        "desarrolla una capa límite de 0,02 m de espesor con perfil de velocidades lineal, para el que el "
        "espesor de desplazamiento es la mitad del espesor de la capa. Calcula el espesor de "
        "desplazamiento."
    ),
    "instrumentacion": (
        "Presión dinámica del aire. El aire de densidad 1,225 kg/m³ circula a 10 m/s. Calcula la presión "
        "dinámica que registra un tubo de Pitot y exprésala en pascales."
    ),
}

# The practice prompts, base exercise first and extension second, with the raw
# expressions removed for the same reason.
PRACTICE_PROMPTS: dict[str, list[str]] = {
    "introduccion": [
        (
            "Peso específico del agua dulce. Con densidad 998 kg/m³ y gravedad 9,81 m/s², calcula el peso "
            "específico del agua y exprésalo en newtons por metro cúbico."
        ),
        (
            "Peso de un volumen de aire. Con densidad 1,225 kg/m³ y gravedad 9,81 m/s², calcula el peso de "
            "2 m³ de aire y exprésalo en newtons."
        ),
    ],
    "propiedades": [
        (
            "Viscosidad cinemática del aire. Para aire con viscosidad dinámica 0,0000181 Pa·s y densidad "
            "1,225 kg/m³, calcula su viscosidad cinemática."
        ),
        (
            "Viscosidad dinámica a partir de una tensión cortante. Si sobre un fluido actúa una tensión "
            "cortante de 2 Pa y el gradiente de velocidad vale 500 por segundo, calcula la viscosidad "
            "dinámica y exprésala en pascales por segundo."
        ),
    ],
    "estatica": [
        (
            "Presión hidrostática a veinte metros de profundidad. Con densidad 998 kg/m³ y gravedad "
            "9,81 m/s², calcula la presión manométrica a 20 m."
        ),
        (
            "Empuje sobre un cuerpo sumergido. Un cuerpo desaloja 0,02 m³ de agua de densidad 998 kg/m³ bajo "
            "gravedad 9,81 m/s². Calcula el empuje de Arquímedes y exprésalo en newtons."
        ),
    ],
    "continuidad": [
        (
            "Velocidad en un estrechamiento. El mismo caudal de 0,02 m³/s atraviesa una sección de "
            "0,005 m². Calcula la velocidad y exprésala en metros por segundo."
        ),
        (
            "Caudal por una sección mayor. Para un área de 0,03 m² y una velocidad de 4 m/s, calcula el "
            "caudal y exprésalo en metros cúbicos por segundo."
        ),
    ],
    "bernoulli": [
        "Torricelli con mayor altura. Repite el cálculo de la energía cinética específica para una profundidad de 10 m.",
        "Torricelli con poca altura. Repite el cálculo de la energía cinética específica para una profundidad de 2 m.",
    ],
    "momentum": [
        "Fuerza con cambio de velocidad mayor. Repite el cálculo de la fuerza sobre el codo para un cambio de velocidad de 3 m/s.",
        (
            "Fuerza con sección mayor. El agua de densidad 998 kg/m³ circula por una sección de 0,02 m² a "
            "1 m/s y cambia su velocidad en 1 m/s. Calcula la fuerza sobre el codo."
        ),
    ],
    "reynolds": [
        (
            "Número de Reynolds del aire. Para aire con densidad 1,225 kg/m³ que circula a 50 m/s por un "
            "conducto de 1 m de diámetro y viscosidad dinámica 0,0000181 Pa·s, calcula el número de "
            "Reynolds."
        ),
        (
            "Número de Reynolds del agua con menor diámetro. Para agua con densidad 998 kg/m³ que circula a "
            "1,5 m/s por un tubo de 0,05 m de diámetro y viscosidad dinámica 0,001 Pa·s, calcula el número "
            "de Reynolds."
        ),
    ],
    "tuberias": [
        "Velocidad media con otro caudal. Repite el cálculo para un caudal de 0,03 m³/s y una sección de 0,01 m².",
        "Velocidad media con un caudal mayor. Repite el cálculo para un caudal de 0,06 m³/s y una sección de 0,01 m².",
    ],
    "capa-limite": [
        (
            "Espesor de desplazamiento de un perfil parabólico. Para una capa límite de 0,06 m de espesor "
            "con perfil parabólico, el espesor de desplazamiento vale un tercio del espesor. Calcula ese "
            "espesor."
        ),
        (
            "Espesor de desplazamiento de una capa más gruesa. Para una capa límite de 0,1 m de espesor con "
            "perfil lineal, calcula el espesor de desplazamiento."
        ),
    ],
    "instrumentacion": [
        "Presión dinámica a mayor velocidad. Repite el cálculo para una velocidad de 20 m/s.",
        "Presión dinámica a baja velocidad. Para aire de densidad 1,225 kg/m³ que circula a 5 m/s, calcula la presión dinámica.",
    ],
}

# The kind of reasoning each problem exercises, so a chapter's variety can be
# audited instead of assumed.
WORKED_TYPES: dict[str, str] = {
    "introduccion": "APPLICATION",
    "propiedades": "MULTI_STEP",
    "estatica": "APPLICATION",
    "continuidad": "APPLICATION",
    "bernoulli": "MULTI_STEP",
    "momentum": "MULTI_STEP",
    "reynolds": "INTERPRETATION",
    "tuberias": "APPLICATION",
    "capa-limite": "SYMBOLIC",
    "instrumentacion": "APPLICATION",
}
WORKED_DIFFICULTIES: dict[str, str] = {
    "introduccion": "INTERMEDIATE",
    "propiedades": "INTERMEDIATE",
    "estatica": "INTERMEDIATE",
    "continuidad": "FOUNDATIONAL",
    "bernoulli": "ADVANCED",
    "momentum": "ADVANCED",
    "reynolds": "ADVANCED",
    "tuberias": "FOUNDATIONAL",
    "capa-limite": "ADVANCED",
    "instrumentacion": "INTERMEDIATE",
}
PRACTICE_TYPES: dict[str, list[str]] = {
    "introduccion": ["APPLICATION", "APPLICATION"],
    "propiedades": ["NUMERICAL", "SYMBOLIC"],
    "estatica": ["APPLICATION", "APPLICATION"],
    "continuidad": ["APPLICATION", "APPLICATION"],
    "bernoulli": ["NUMERICAL", "NUMERICAL"],
    "momentum": ["NUMERICAL", "APPLICATION"],
    "reynolds": ["NUMERICAL", "INTERPRETATION"],
    "tuberias": ["NUMERICAL", "NUMERICAL"],
    "capa-limite": ["NUMERICAL", "APPLICATION"],
    "instrumentacion": ["NUMERICAL", "NUMERICAL"],
}

# A structured, multi-step engineering solution for each worked problem. The
# symbolic model is verified from the record; the substitution is generated
# from that model and the given quantities, so the displayed equation and the
# checked computation cannot drift apart.
EXTRA_SOLUTIONS: dict[str, dict[str, object]] = {
    "introduccion": {
        "given": [
            {"symbol": "rho", "value": "1.225", "unit": "kg/m^3", "meaning": "densidad del aire en condiciones estándar"},
            {"symbol": "g", "value": "9.81", "unit": "m/s^2", "meaning": "aceleración de la gravedad"},
        ],
        "unknown": "peso específico gamma del aire, en newtons por metro cúbico",
        "model": [{"name": "Peso específico", "latex": r"\gamma = \rho\, g", "symbolic": "rho*g"}],
        "assumptions": [
            "el aire se trata como medio continuo de densidad uniforme",
            "la gravedad es constante en todo el volumen considerado",
        ],
        "steps": [
            {"text": "Se identifica el peso específico con el producto de la densidad por la aceleración de la gravedad.", "equation": r"\gamma = \rho\, g"},
            {"text": "Se sustituyen los valores medidos y se conserva la unidad del sistema internacional.", "expression": "1.225*9.81", "unit": "N/m^3"},
        ],
        "result": r"\gamma = 12.02\,\mathrm{N\,m^{-3}}",
        "interpretation": "Cada metro cúbico de aire pesa unos 12,02 N; al ser tan pequeño frente al del agua, solo se aprecia en volúmenes grandes.",
        "limitations": ["a gran altitud la densidad del aire disminuye y el peso específico baja", "no se aplica a la capa de aire tan enrarecida como para perder el medio continuo"],
        "mistakes": ["confundir la densidad (kg/m³) con el peso específico (N/m³)", "olvidar que la unidad procede de multiplicar kg/m³ por m/s²"],
    },
    "propiedades": {
        "given": [
            {"symbol": "mu", "value": "0.001", "unit": "Pa*s", "meaning": "viscosidad dinámica del agua a 20 °C"},
            {"symbol": "rho", "value": "998", "unit": "kg/m^3", "meaning": "densidad del agua a 20 °C"},
        ],
        "unknown": "viscosidad cinemática nu, en metros cuadrados por segundo",
        "model": [{"name": "Viscosidad cinemática", "latex": r"\nu = \frac{\mu}{\rho}", "symbolic": "mu/rho"}],
        "assumptions": ["fluido newtoniano", "densidad uniforme y temperatura constante"],
        "steps": [
            {"text": "Se parte de la definición de viscosidad cinemática como cociente entre la viscosidad dinámica y la densidad.", "equation": r"\nu = \frac{\mu}{\rho}"},
            {"text": "Se sustituyen las propiedades del agua a 20 °C.", "expression": "0.001/998", "unit": "m^2/s"},
        ],
        "result": r"\nu = 1.002\times10^{-6}\,\mathrm{m^{2}\,s^{-1}}",
        "interpretation": "El agua difunde cantidad de movimiento muy lentamente; este valor se usa para calcular el número de Reynolds del agua en tuberías.",
        "limitations": ["la viscosidad depende fuertemente de la temperatura; el valor solo vale cerca de 20 °C", "no describe fluidos no newtonianos sin correcciones"],
        "mistakes": ["invertir el cociente y dividir la densidad entre la viscosidad", "mezclar las unidades de Pa·s con las de kg/(m·s)"],
    },
    "estatica": {
        "given": [
            {"symbol": "rho", "value": "998", "unit": "kg/m^3", "meaning": "densidad del agua dulce"},
            {"symbol": "g", "value": "9.81", "unit": "m/s^2", "meaning": "aceleración de la gravedad"},
            {"symbol": "h", "value": "10", "unit": "m", "meaning": "profundidad bajo la superficie libre"},
        ],
        "unknown": "presión manométrica p en el seno del agua, en pascales",
        "model": [{"name": "Ecuación fundamental de la hidrostática", "latex": r"p = p_0 + \rho\, g\, h", "symbolic": "rho*g*h"}],
        "assumptions": ["fluido en reposo", "densidad uniforme", "gravedad constante"],
        "steps": [
            {"text": "En un fluido en reposo la presión crece con la profundidad según el peso de la columna de agua.", "equation": r"p = p_0 + \rho\, g\, h"},
            {"text": "Se toma p0 como presión atmosférica y se calcula la sobrepresión debida a la columna.", "expression": "998*9.81*10", "unit": "Pa"},
        ],
        "result": r"p - p_0 = 9.79\times10^{4}\,\mathrm{Pa}",
        "interpretation": "Diez metros de agua añaden casi una atmósfera (1 atm = 101 325 Pa) de presión manométrica, por eso un buceador nota la presión al descender.",
        "limitations": ["supone el agua incompresible y de densidad constante, válido a pocos kilómetros de profundidad", "no incluye la presión atmosférica si se pide la presión absoluta"],
        "mistakes": ["sumar la profundidad en centímetros sin convertirla a metros", "confundir presión manométrica con presión absoluta"],
    },
    "continuidad": {
        "given": [
            {"symbol": "A", "value": "0.01", "unit": "m^2", "meaning": "área de la sección recta"},
            {"symbol": "V", "value": "2", "unit": "m/s", "meaning": "velocidad media del agua"},
        ],
        "unknown": "caudal volumétrico Q, en metros cúbicos por segundo",
        "model": [{"name": "Caudal volumétrico", "latex": r"Q = A\, V", "symbolic": "A*V"}],
        "assumptions": ["flujo estacionario", "velocidad uniforme en la sección", "fluido incompresible"],
        "steps": [
            {"text": "El caudal es el volumen que atraviesa la sección por unidad de tiempo, igual al área por la velocidad.", "equation": r"Q = A\, V"},
            {"text": "Se sustituyen el área y la velocidad dadas.", "expression": "0.01*2", "unit": "m^3/s"},
        ],
        "result": r"Q = 0.020\,\mathrm{m^{3}\,s^{-1}}",
        "interpretation": "Por la tubería pasan 20 litros de agua cada segundo; el caudal se conserva aguas abajo salvo en un depósito.",
        "limitations": ["el perfil de velocidades real no es uniforme; la velocidad es la media de la sección", "en régimen no estacionario el caudal puede cambiar con el tiempo"],
        "mistakes": ["multiplicar el diámetro en lugar del área", "usar el área en centímetros cuadrados sin convertir"],
    },
    "bernoulli": {
        "given": [
            {"symbol": "g", "value": "9.81", "unit": "m/s^2", "meaning": "aceleración de la gravedad"},
            {"symbol": "h", "value": "5", "unit": "m", "meaning": "altura del líquido sobre el orificio"},
        ],
        "unknown": "energía cinética específica V² y velocidad de salida V, en metros por segundo",
        "model": [{"name": "Torricelli", "latex": r"V^{2} = 2\, g\, h", "symbolic": "2*g*h"}],
        "assumptions": ["depósito abierto a la atmósfera", "fluido ideal sin viscosidad", "régimen estacionario", "orificio pequeño frente a la sección del depósito"],
        "steps": [
            {"text": "Al aplicar Bernoulli entre la superficie libre y el orificio, la presión vale la atmosférica en ambos puntos y la velocidad en la superficie es despreciable.", "equation": r"p_{atm} + \rho g h = p_{atm} + \tfrac{1}{2}\rho V^{2}"},
            {"text": "Se simplifica y queda el cuadrado de la velocidad igual a dos veces g por h.", "expression": "2*9.81*5", "unit": "m^2/s^2"},
            {"text": "Se toma la raíz cuadrada para obtener la velocidad de salida.", "equation": r"V = \sqrt{2\, g\, h} = \sqrt{98.1} \approx 9.90\,\mathrm{m\,s^{-1}}"},
        ],
        "result": r"V = 9.90\,\mathrm{m\,s^{-1}}",
        "interpretation": "La velocidad de salida no depende de la densidad del líquido ni del tamaño del orificio, solo de la altura de carga.",
        "limitations": ["ignora las pérdidas por viscosidad y el coeficiente de contracción del chorro", "deja de ser válido si el orificio no es pequeño frente al depósito"],
        "mistakes": ["olvidar el factor 2 de 2gh", "calcular V² y presentarlo como la velocidad sin extraer la raíz"],
    },
    "momentum": {
        "given": [
            {"symbol": "rho", "value": "998", "unit": "kg/m^3", "meaning": "densidad del agua"},
            {"symbol": "A", "value": "0.01", "unit": "m^2", "meaning": "área de la sección de entrada"},
            {"symbol": "V", "value": "2", "unit": "m/s", "meaning": "velocidad de entrada"},
            {"symbol": "dV", "value": "2", "unit": "m/s", "meaning": "cambio de velocidad en la dirección de la corriente"},
        ],
        "unknown": "fuerza del fluido sobre el codo, en newtons",
        "model": [{"name": "Cantidad de movimiento", "latex": r"F = \rho\, A\, V\, \Delta V", "symbolic": "rho*A*V*dV"}],
        "assumptions": ["flujo estacionario", "fluido incompresible", "presión atmosférica uniforme en la salida"],
        "steps": [
            {"text": "La fuerza es el flujo másico por el cambio de velocidad: la masa que pasa por segundo cambia su cantidad de movimiento.", "equation": r"F = \dot{m}\, \Delta V = \rho\, A\, V\, \Delta V"},
            {"text": "Se sustituyen la densidad, la sección, la velocidad y el cambio de velocidad.", "expression": "998*0.01*2*2", "unit": "N"},
        ],
        "result": r"F = 39.92\,\mathrm{N}",
        "interpretation": "El codo debe anclarse para soportar unos 40 N; la fuerza crece con el cuadrado de la velocidad porque el flujo másico y el cambio de velocidad aumentan a la vez.",
        "limitations": ["no incluye la fuerza de presión si la sección cambia", "supone régimen estacionario y ausencia de pérdidas"],
        "mistakes": ["olvidar el flujo másico y usar solo el cambio de velocidad", "aplicar la fórmula a una sección que cambia de área sin corregir"],
    },
    "reynolds": {
        "given": [
            {"symbol": "rho", "value": "998", "unit": "kg/m^3", "meaning": "densidad del agua a 20 °C"},
            {"symbol": "V", "value": "2", "unit": "m/s", "meaning": "velocidad media en la tubería"},
            {"symbol": "D", "value": "0.1", "unit": "m", "meaning": "diámetro interior de la tubería"},
            {"symbol": "mu", "value": "0.001", "unit": "Pa*s", "meaning": "viscosidad dinámica del agua a 20 °C"},
        ],
        "unknown": "número de Reynolds Re, adimensional",
        "model": [{"name": "Número de Reynolds", "latex": r"\mathrm{Re} = \frac{\rho\, V\, D}{\mu}", "symbolic": "rho*V*D/mu"}],
        "assumptions": ["viscosidad constante", "el diámetro es la longitud característica", "conducto circular lleno"],
        "steps": [
            {"text": "El número de Reynolds compara las fuerzas de inercia con las viscosas.", "equation": r"\mathrm{Re} = \frac{\rho\, V\, D}{\mu}"},
            {"text": "Se sustituyen las propiedades del agua y los datos de la tubería.", "expression": "998*2*0.1/0.001", "unit": "adimensional"},
        ],
        "result": r"\mathrm{Re} = 1.996\times10^{5}",
        "interpretation": "Con Re próximo a 2×10⁵ el flujo está plenamente turbulento: en una tubería circular la transición se sitúa alrededor de Re = 2300.",
        "limitations": ["la longitud característica cambia según el problema (diámetro, cuerda, longitud de placa)", "el valor de transición depende del régimen de entrada y de la rugosidad"],
        "mistakes": ["dejar unidades sin cancelar y obtener un resultado dimensional", "usar el radio en lugar del diámetro como longitud característica"],
    },
    "tuberias": {
        "given": [
            {"symbol": "Q", "value": "0.02", "unit": "m^3/s", "meaning": "caudal volumétrico"},
            {"symbol": "A", "value": "0.01", "unit": "m^2", "meaning": "área de la sección recta"},
        ],
        "unknown": "velocidad media V, en metros por segundo",
        "model": [{"name": "Velocidad media", "latex": r"V = \frac{Q}{A}", "symbolic": "Q/A"}],
        "assumptions": ["flujo estacionario incompresible", "sección constante"],
        "steps": [
            {"text": "De la definición de caudal se despeja la velocidad media dividiendo por el área.", "equation": r"V = \frac{Q}{A}"},
            {"text": "Se sustituyen el caudal y el área.", "expression": "0.02/0.01", "unit": "m/s"},
        ],
        "result": r"V = 2.0\,\mathrm{m\,s^{-1}}",
        "interpretation": "Con esta velocidad media y el diámetro de la tubería se puede comprobar el régimen de flujo con el número de Reynolds.",
        "limitations": ["la velocidad es la media de la sección; el perfil real es parabólico en régimen laminar", "no tiene en cuenta la rugosidad ni los accidentes de la conducción"],
        "mistakes": ["multiplicar en lugar de dividir entre el área", "mezclar el caudal en litros por segundo con el área en metros cuadrados"],
    },
    "capa-limite": {
        "given": [
            {"symbol": "delta", "value": "0.02", "unit": "m", "meaning": "espesor de la capa límite sobre la placa"},
        ],
        "unknown": "espesor de desplazamiento delta* , en metros",
        "model": [{"name": "Espesor de desplazamiento, perfil lineal", "latex": r"\delta^{*} = \frac{\delta}{2}", "symbolic": "delta/2"}],
        "assumptions": ["perfil de velocidades lineal dentro de la capa", "corriente libre uniforme"],
        "steps": [
            {"text": "El déficit de caudal de un perfil lineal respecto al flujo ideal equivale a la mitad del espesor.", "equation": r"\delta^{*} = \int_{0}^{\delta}\left(1 - \frac{y}{\delta}\right) dy = \frac{\delta}{2}"},
            {"text": "Se sustituye el espesor medido de la capa.", "expression": "0.02/2", "unit": "m"},
        ],
        "result": r"\delta^{*} = 0.010\,\mathrm{m}",
        "interpretation": "La capa límite desplaza hacia fuera del cuerpo el flujo una distancia equivalente a la mitad de su espesor, lo que engrosa la forma efectiva.",
        "limitations": ["el perfil lineal es una idealización; el perfil real es más afín a una ley de potencias o a Blasius", "no describe la zona separada aguas abajo"],
        "mistakes": ["confundir el espesor de la capa con el espesor de desplazamiento", "aplicar el factor 1/2 a un perfil que no es lineal"],
    },
    "instrumentacion": {
        "given": [
            {"symbol": "rho", "value": "1.225", "unit": "kg/m^3", "meaning": "densidad del aire"},
            {"symbol": "V", "value": "10", "unit": "m/s", "meaning": "velocidad de la corriente de aire"},
        ],
        "unknown": "presión dinámica q, en pascales",
        "model": [{"name": "Presión dinámica", "latex": r"q = \tfrac{1}{2}\, \rho\, V^{2}", "symbolic": "rho*V**2/2"}],
        "assumptions": ["flujo incompresible", "medición en el punto de remanso isoentrópica"],
        "steps": [
            {"text": "La presión dinámica es la energía cinética por unidad de volumen del aire en movimiento.", "equation": r"q = \tfrac{1}{2}\, \rho\, V^{2}"},
            {"text": "Se sustituyen la densidad del aire y el cuadrado de la velocidad.", "expression": "0.5*1.225*100", "unit": "Pa"},
        ],
        "result": r"q = 61.25\,\mathrm{Pa}",
        "interpretation": "El tubo de Pitot mide esta sobrepresión; con q y la densidad se recupera la velocidad del aire mediante Bernoulli.",
        "limitations": ["a alta velocidad el aire se comprime y hay que corregir por compresibilidad", "la lectura depende de la alineación de la sonda con la corriente"],
        "mistakes": ["olvidar elevar la velocidad al cuadrado", "usar la densidad del agua en una corriente de aire"],
    },
}

# Typeset intermediate steps for each derivation, keyed by equation id. The
# symbolic form lets the engine substitute values and check the identity.
DERIVATION_LATEX: dict[str, dict[str, object]] = {
    "eq-peso-especifico": {
        "symbolic": "rho*g",
        "steps_latex": [
            r"m = \rho\, V",
            r"W = m\, g = \rho\, V\, g",
            r"\gamma = \frac{W}{V} = \rho\, g",
        ],
    },
    "eq-viscosidad-cinematica": {
        "symbolic": "mu/rho",
        "steps_latex": [
            r"\tau = \mu\, \frac{du}{dy}",
            r"\nu = \frac{\mu}{\rho}",
        ],
    },
    "eq-hidrostatica": {
        "symbolic": "p0 + rho*g*h",
        "steps_latex": [
            r"p\, A - (p + dp)\, A - \rho\, g\, A\, dh = 0",
            r"\frac{dp}{dh} = -\,\rho\, g",
            r"p = p_0 + \rho\, g\, h",
        ],
    },
    "eq-continuidad": {
        "symbolic": "A1*V1",
        "steps_latex": [
            r"\rho\, A_1\, V_1 = \rho\, A_2\, V_2",
            r"A_1\, V_1 = A_2\, V_2",
            r"V_2 = \frac{A_1}{A_2}\, V_1",
        ],
    },
    "eq-torricelli": {
        "symbolic": "2*g*h",
        "steps_latex": [
            r"p_1 + \tfrac{1}{2}\rho V_1^{2} + \rho g z_1 = p_2 + \tfrac{1}{2}\rho V_2^{2} + \rho g z_2",
            r"p_{atm} + \rho g h = p_{atm} + \tfrac{1}{2}\rho V^{2}",
            r"V = \sqrt{2\, g\, h}",
        ],
    },
    "eq-rtt": {
        "symbolic": None,
        "steps_latex": [
            r"\frac{d}{dt}\int_{V_m} \rho\, dV = \frac{\partial}{\partial t}\int_{V} \rho\, dV + \oint_{S} \rho\, \vec{V}\cdot d\vec{S}",
            r"\frac{D}{Dt}\int_{V} b\, \rho\, dV = \int_{V} \frac{\partial}{\partial t}(b\, \rho)\, dV + \oint_{S} b\, \rho\, \vec{V}\cdot d\vec{S}",
        ],
    },
    "eq-reynolds": {
        "symbolic": "rho*V*D/mu",
        "steps_latex": [
            r"\text{inercia} \sim \rho\, \frac{V^{2}}{D}",
            r"\text{viscoso} \sim \mu\, \frac{V}{D^{2}}",
            r"\mathrm{Re} = \frac{\rho V D}{\mu}",
        ],
    },
    "eq-poiseuille": {
        "symbolic": "pi*dp*r**4/(8*mu*L)",
        "steps_latex": [
            r"\pi r^{2}\, \Delta p = 2\pi r L\, \tau",
            r"\tau = -\,\mu\, \frac{dv}{dr}",
            r"v(r) = \frac{\Delta p}{4\mu L}\left(r_0^{2} - r^{2}\right)",
            r"Q = \int_{0}^{r_0} v(r)\, 2\pi r\, dr = \frac{\pi\, \Delta p\, r_0^{4}}{8\mu L}",
        ],
    },
    "eq-espesor-desplazamiento": {
        "symbolic": None,
        "steps_latex": [
            r"Q_{ideal} = U\, \delta",
            r"Q_{real} = \int_{0}^{\delta} V(y)\, dy",
            r"\delta^{*} = \int_{0}^{\delta}\left(1 - \frac{V}{U}\right) dy",
        ],
    },
    "eq-pitot": {
        "symbolic": "2*(pt-ps)/rho",
        "steps_latex": [
            r"p_t = p_s + \tfrac{1}{2}\rho V^{2}",
            r"\tfrac{1}{2}\rho V^{2} = p_t - p_s",
            r"V = \sqrt{\frac{2\,(p_t - p_s)}{\rho}}",
        ],
    },
}


def _academic_parts() -> list[dict[str, object]]:
    sections = {item["id"]: item for item in BLUEPRINT}
    parts: list[dict[str, object]] = []
    for part_id, part_title, section_ids in ACADEMIC_PARTS:
        chapters: list[dict[str, object]] = []
        for section_id in section_ids:
            concepts = [
                {
                    "id": concept_id,
                    "title": concept_title,
                    "learning_objectives": [f"comprender y aplicar: {concept_title.lower()}"],
                    "depth": "ADVANCED_UNDERGRADUATE",
                    "exercises": 2,
                }
                for concept_id, concept_title in CONCEPTS[section_id]
            ]
            chapters.append(
                {
                    "id": section_id,
                    "title": sections[section_id]["title"],
                    "learning_objectives": [f"comprender {sections[section_id]['title'].lower()}"],
                    "sections": [
                        {
                            "id": f"{section_id}.1",
                            "title": sections[section_id]["title"].split(":")[0],
                            "concepts": concepts,
                        }
                    ],
                }
            )
        parts.append({"id": part_id, "title": part_title, "chapters": chapters})
    return parts


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


def _paragraph(
    session, section: str, text: str, excerpt_ids: list[str], concepts: list[str], role: str = "explanation"
) -> str:
    recorded = dispatch(
        "studium_paragraph_record",
        {"section": section, "text": text, "excerpts": excerpt_ids, "role": role, "concepts": concepts},
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


def _solution_with_expected(solution: dict[str, object]) -> dict[str, object]:
    """Deep-copy a solution and fill each computational step's expected value.

    The expected value is derived by the server's own evaluator, so the prose
    can never quote an arithmetic result the engine did not reproduce.
    """
    filled = json.loads(json.dumps(solution, ensure_ascii=False))
    for step in filled.get("steps", []):
        if not isinstance(step, dict) or "expression" not in step:
            continue
        if "expected" not in step or step["expected"] in (None, ""):
            step["expected"] = _decimal_answer(evaluate(step["expression"]))
    return filled


def _problem(
    session,
    section: str,
    prompt: str,
    expected: str,
    excerpt_ids: list[str],
    *,
    role: str = "worked",
    difficulty: str | None = None,
    objectives: list[str] | None = None,
    problem_type: str | None = None,
    solution: dict[str, object] | None = None,
) -> str:
    params: dict[str, object] = {
        "section": section,
        "prompt": prompt,
        "expected": expected,
        "excerpts": excerpt_ids,
        "role": role,
    }
    if difficulty is not None:
        params["difficulty"] = difficulty
    if objectives is not None:
        params["learning_objectives"] = objectives
    if problem_type is not None:
        params["problem_type"] = problem_type
    if solution is not None:
        params["solution"] = _solution_with_expected(solution)
    recorded = dispatch("studium_problem_record", params, session=session)
    if recorded.get("problem", {}).get("status") != "two_witnesses":
        raise AssertionError(f"problem not two_witnesses: {json.dumps(recorded, ensure_ascii=False)[:1200]}")
    problem_id = str(recorded["problem"]["id"])
    if solution is not None:
        checked = dispatch("studium_problem_check", {"id": problem_id}, session=session)
        if checked.get("steps_reproduced") is not True:
            raise AssertionError(f"solution steps not reproduced: {json.dumps(checked, ensure_ascii=False)[:1200]}")
    return problem_id


def _derivation(session, section: str, data: dict[str, object]) -> str:
    merged = dict(data)
    extra = DERIVATION_LATEX.get(str(data.get("equation_id") or ""))
    if extra:
        for key, value in extra.items():
            if value is not None and key not in merged:
                merged[key] = value
    params: dict[str, object] = {
        "section": section,
        "name": merged["name"],
        "equation": merged["equation"],
        "equation_id": merged["equation_id"],
        "assumptions": merged["assumptions"],
        "governing_principles": merged["governing_principles"],
        "steps": merged["steps"],
        "variables": merged["variables"],
        "limitations": merged["limitations"],
    }
    if merged.get("steps_latex"):
        params["steps_latex"] = merged["steps_latex"]
    if merged.get("symbolic"):
        params["symbolic"] = merged["symbolic"]
    recorded = dispatch("studium_derivation_record", params, session=session)
    assert recorded["status"] == "recorded", recorded
    derivation_id = str(recorded["derivation"]["id"])
    check = data.get("check")
    if check:
        checked = dispatch("studium_derivation_check", {"id": derivation_id, **check}, session=session)
        assert checked["status"] == "checked", checked
        assert checked["verification_status"] != "FAILED", checked
    return derivation_id


def _notation(session, section: str, entry: dict[str, object]) -> None:
    recorded = dispatch(
        "studium_notation_record",
        {
            "section": section,
            "symbol": entry["symbol"],
            "meaning": entry["meaning"],
            "units": entry["units"],
        },
        session=session,
    )
    assert recorded["status"] == "recorded", recorded


def _terminology(session, section: str, entry: dict[str, object]) -> None:
    recorded = dispatch(
        "studium_terminology_record",
        {"section": section, "term": entry["term"], "definition": entry["definition"]},
        session=session,
    )
    assert recorded["status"] == "recorded", recorded


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

    academic = dispatch(
        "studium_academic_blueprint_store",
        {"profile_key": "ADVANCED_UNDERGRADUATE", "subject": COURSE["course"], "parts": _academic_parts()},
        session=session,
    )
    assert academic["status"] == "recorded", academic

    planned = dispatch(
        "studium_depth_plan",
        {"academic_depth": "ADVANCED_UNDERGRADUATE", "length": "COMPREHENSIVE", "target_pages": 60},
        session=session,
    )
    assert planned["status"] == "planned", planned

    excerpts: dict[str, str] = {}
    for item in SOURCES:
        excerpts[item["id"]] = _record_source_and_excerpt(session, item)

    computation_ids: dict[str, str] = {}
    problem_ids: dict[str, list[str]] = {}
    derivation_ids: dict[str, list[str]] = {}

    for section_id, section_data in SECTIONS.items():
        concepts = [concept_id for concept_id, _title in CONCEPTS[section_id]]
        section_excerpts = [excerpts[i] for i in section_data["excerpts"]]

        plan: list[tuple[str, str]] = [(text, "explanation") for text in section_data["paragraphs"]]
        prose = EXTRA_PROSE.get(section_id, {})
        if "definition" in prose:
            plan.append((prose["definition"], "definition"))
        if "self_check" in prose:
            plan.append((prose["self_check"], "self_check"))
        plan.extend((text, "explanation") for text in prose.get("extra", []))
        for text, role in plan:
            _paragraph(session, section_id, text, section_excerpts, concepts, role)

        worked = section_data["worked"]
        computation_id, _worked_expected = _computation(session, section_id, worked["expression"])
        computation_ids[section_id] = computation_id
        problem_ids.setdefault(section_id, []).append(
            _problem(
                session,
                section_id,
                WORKED_PROMPTS.get(section_id, worked["prompt"]),
                _decimal_answer(evaluate(worked["expression"])),
                [excerpts[i] for i in worked["excerpts"]],
                role="worked",
                difficulty=worked.get("difficulty") or WORKED_DIFFICULTIES.get(section_id),
                problem_type=WORKED_TYPES.get(section_id),
                solution=EXTRA_SOLUTIONS.get(section_id),
            )
        )

        practices = list(section_data["practice"]) + list(EXTRA_PRACTICE.get(section_id, []))
        practice_prompts = PRACTICE_PROMPTS.get(section_id, [])
        practice_types = PRACTICE_TYPES.get(section_id, [])
        for index, practice in enumerate(practices):
            prompt = practice_prompts[index] if index < len(practice_prompts) else practice["prompt"]
            problem_type = practice_types[index] if index < len(practice_types) else practice.get("problem_type")
            problem_ids.setdefault(section_id, []).append(
                _problem(
                    session,
                    section_id,
                    prompt,
                    _decimal_answer(evaluate(practice["expression"])),
                    [excerpts[i] for i in practice["excerpts"]],
                    role="practice",
                    difficulty=practice["difficulty"],
                    objectives=practice["objectives"],
                    problem_type=problem_type,
                )
            )

        for derivation in list(section_data.get("derivations", [])) + list(EXTRA_DERIVATIONS.get(section_id, [])):
            derivation_ids.setdefault(section_id, []).append(_derivation(session, section_id, derivation))

        for entry in section_data.get("notation", []):
            _notation(session, section_id, entry)

        for entry in section_data.get("terminology", []):
            _terminology(session, section_id, entry)

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

    report = dispatch("studium_quality_report", {}, session=session)
    assert report["status"] == "ok", report

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
- `bibliography/` — las {len(SOURCES)} fuentes públicas registradas y sus excerptos.
- `blueprint/` — el esquema (outline) con las {len(BLUEPRINT)} secciones y el plan de profundidad.
- `draft/` — párrafos, derivaciones, notación, auditorías, escaneo de contradicciones y revisiones.
- `problems/` — comprobaciones aritméticas reproducidas y problemas trabajados y de práctica.
- `latex/draft.pdf` — el PDF compilado de este libro.
- `sources.json` — lista de fuentes con URL, licencia y texto recogido.

## Cómo se construyó

```
source venv/bin/activate
python examples/build-fluid-mechanics-ule.py
```

El guion `../build-fluid-mechanics-ule.py` reproduce el libro sin red y sin
modelos externos: registra las fuentes, guarda el esquema de {len(BLUEPRINT)}
secciones, escribe el plan de profundidad y el plan académico, redacta los
párrafos, reproduce las comprobaciones aritméticas (`expr = valor` lo vuelve a
evaluar el propio servidor), registra las derivaciones con sus comprobaciones
simbólicas, numéricas y dimensionales, los problemas trabajados y de práctica,
la notación y la terminología, audita cada sección, escanea contradicciones,
revisa la edición y compila `latex/draft.pdf` con LaTeX.

## Fuentes

Las {len(SOURCES)} fuentes (URL y licencia en `sources.json`) se recuperaron el
2026-10-09. Los textos registrados son fragmentos verbatim cortos de esas
páginas: NASA Glenn (dominio público), Wikipedia en español (CC BY-SA 4.0),
LibreTexts Español (CC BY-SA 4.0) y MIT OpenCourseWare (CC BY-NC-SA 4.0). No
hay grandes pasajes protegidos por derechos de autor; las citas se limitan a
una o dos frases y el resto del texto es redacción original del libro.
"""
    (BOOK / "README.md").write_text(readme, encoding="utf-8")


def write_quality_report() -> dict[str, object]:
    """Write QUALITY.md from the measured pipeline reports and the compiled PDF.

    Every number is taken from a stored record or from the compiled PDF; the
    report never invents a metric and it never claims academic review.
    """

    session = open_workspace(str(EXAMPLES))
    assert session is not None
    session.active = BOOK

    report = dispatch("studium_quality_report", {}, session=session)
    assert report["status"] == "ok", report
    counts = report["counts"]
    completeness = report["completeness"]
    coverage = report["coverage"]
    statuses = report["derivation_statuses"]

    log_text = (BOOK / "latex" / "draft.log").read_text(encoding="utf-8", errors="replace")
    flat = re.sub(r"\s+", " ", log_text)
    error_count = len(re.findall(r"^!", log_text, re.M))
    overfull = len(re.findall(r"Overfull \\hbox", log_text))
    pages_match = re.search(r"\((\d+) pages", flat)
    pages = pages_match.group(1) if pages_match else "desconocido"

    plan_status = dispatch("studium_depth_plan_status", {}, session=session)
    length_plan = plan_status.get("plan", {}).get("length") if plan_status.get("status") == "ok" else None
    match: dict[str, object] | None = None
    if isinstance(length_plan, dict) and length_plan.get("low") and pages.isdigit():
        scope = LengthScope(
            estimate=float(length_plan["estimate"]),
            floor=float(length_plan["low"]),
            ceiling=float(length_plan["high"]),
            preference=str(length_plan["preference"]),
            breakdown={key: float(value) for key, value in dict(length_plan.get("breakdown", {})).items()},
        )
        match = assess_length_match(scope=scope, actual_pages=int(pages))

    length_rows: list[str] = []
    length_note: list[str] = []
    if match is not None:
        length_rows = [
            f"| Páginas planificadas (rango) | {float(match['floor']):.0f}–{float(match['ceiling']):.0f} |",
            f"| Veredicto de longitud | {match['verdict']} |",
        ]
        length_note = [
            f"El plan de profundidad declara un ámbito {match['preference']} de "
            f"{float(match['floor']):.0f}–{float(match['ceiling']):.0f} páginas. "
            f"El PDF medido tiene {pages} páginas y el veredicto automático de longitud es "
            f"{match['verdict']}."
        ]

    section_report = dispatch("studium_section_completeness", {}, session=session)
    assert section_report["status"] == "ok", section_report

    lines = [
        "# Informe de calidad — Mecánica de Fluidos (ULE)",
        "",
        "Generado por el propio pipeline a partir de los registros almacenados y del PDF",
        "compilado. No se inventan cifras: todas proceden de `studium_quality_report`,",
        "`studium_section_completeness` y del registro de LaTeX.",
        "",
        "## Métricas del libro",
        "",
        "| Métrica | Valor |",
        "| --- | --- |",
        f"| Capítulos (secciones del esquema) | {counts['sections']} |",
        f"| Capítulos con prosa | {counts['sections_with_prose']} |",
        f"| Capítulos completos (contrato pedagógico) | {completeness['complete']} de {completeness['sections']} |",
        f"| Párrafos | {counts['paragraphs']} |",
        f"| Párrafos auditados | {counts['paragraphs_audited']} |",
        f"| Palabras | {counts['words']} |",
        f"| Fuentes registradas | {counts['sources']} |",
        f"| Extractos usados | {counts['excerpts_used']} |",
        f"| Problemas | {counts['problems']} |",
        f"| Problemas con resultado vigente | {counts['problems_checked']} |",
        f"| Comprobaciones aritméticas reproducidas | {counts['computations_replayed']} |",
        f"| Derivaciones | {counts['derivations']} |",
        f"| Entradas de notación | {counts['notation_entries']} |",
        f"| Términos de glosario | {counts['terminology_entries']} |",
        f"| Cobertura de fuentes | {coverage['sources_used']} de {coverage['sources_recorded']} |",
        f"| Cobertura de conceptos | {coverage['concepts_covered']} de {coverage['concepts_planned']} |",
        f"| Consistencia entre capítulos | {'sí' if report['consistent'] else 'no'} |",
        f"| Contradicciones abiertas | {counts['open_contradictions']} |",
        f"| Páginas medidas del PDF | {pages} |",
        *length_rows,
        f"| Errores de LaTeX (`!`) | {error_count} |",
        f"| Cajas overfull | {overfull} |",
        "",
    ]
    if length_note:
        lines.extend(["## Longitud medida frente al plan", "", *length_note, ""])
    lines.extend(
        [
            "## Estados de verificación de las derivaciones",
            "",
        ]
    )
    for status, count in sorted(statuses.items()):
        lines.append(f"- {status}: {count}")
    lines.extend(
        [
            "",
            "Estos estados los asigna el motor determinista de verificación. No incluyen un",
            "juicio académico humano: la edición no reclama ACADEMICALLY_REVIEWED.",
            "",
            "## Completitud pedagógica por capítulo",
            "",
            "| Capítulo | Completo | Falta |",
            "| --- | --- | --- |",
        ]
    )
    for section in section_report["sections"]:
        missing = ", ".join(section["missing"]) if section["missing"] else "—"
        lines.append(f"| {section['section']} | {'sí' if section['complete'] else 'no'} | {missing} |")
    lines.extend(
        [
            "",
            "## Alcance y límites",
            "",
        ]
    )
    for limitation in report["limitations"]:
        lines.append(f"- {limitation}")
    lines.extend(
        [
            "- El recuento de páginas de la estimación es un cálculo del plan de profundidad;",
            "  el número medido es el del PDF compilado que figura en la tabla anterior.",
            "- Las derivaciones se comprueban de forma simbólica, numérica y dimensional por el",
            "  propio servidor; eso no constituye una demostración formal ni una revisión humana.",
            "",
        ]
    )
    (BOOK / "QUALITY.md").write_text("\n".join(lines), encoding="utf-8")
    return report


if __name__ == "__main__":
    build()
    write_documentation()
    write_quality_report()
    print(f"book ready: {BOOK}")
    print(f"pdf: {BOOK / 'latex' / 'draft.pdf'}")
    engine = find_engine()
    print(f"latex engine: {engine}")
