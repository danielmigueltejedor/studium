# Informe final — Iteración «profundidad académica adaptativa» de Studium

Fecha: 9 de octubre de 2026
Rama: `improve/adaptive-academic-depth` (creada desde `main@7c3a87e`).
Estado: **trabajo sin fusionar y sin liberar**. No hay bump de versión, ni
releases, ni etiquetas, ni push a `main`. La versión del paquete sigue siendo
`1.0.0a1`.

---

## 1. Resumen ejecutivo

Esta iteración construye un motor de autoría de libros **adaptativo en
profundidad académica** dentro de Studium y lo usa para **regenerar por completo**
el libro de texto de Mecánica de Fluidos para el Grado en Ingeniería Aeroespacial
de la Universidad de León. El trabajo se divide en las 18 partes solicitadas;
aquí se agrupan por bloques.

Resultados verificados al cierre (todos medidos en esta sesión):

- **259 pruebas pasan** (`python -m pytest -q`).
- **Ruff: limpio** (`ruff check src tests`).
- **Pyright: 0 errores, 0 avisos** (`pyright`).
- **Cobertura: 76,48 %** sobre `studium`, por encima de la puerta del 75 %
  (`python -m pytest -q --cov=studium --cov-fail-under=75`).
- **Libro compilado**: `examples/fluid-mechanics-ule/latex/draft.pdf`
  (393 805 bytes, 38 páginas, cabecera `%PDF-`).
- **LaTeX limpio**: 0 errores (`!`) y 0 cajas *overfull* en `draft.log`.
- **Completitud pedagógica: 10 de 10 capítulos completos**.
- **Cobertura de fuentes y de conceptos: 21 de 21 y 20 de 20**.
- **0 contradicciones abiertas**; `book_review` con `audit_passed = True` y
  `released = False`.
- **18 herramientas MCP nuevas** cableadas en catálogo y servidor.

La edición se etiqueta honestamente como **edición parcial etiquetada de forma
precisa**: no se reclama revisión humana (`ACADEMICALLY_REVIEWED` nunca se asigna
automáticamente) y el número de páginas medido (38) se contrasta con la
estimación del plan (36,5–65,7).

## 2. Alcance y contexto

Los trabajos se desarrollaron en una copia real de repositorio git
(`studium-src`, rama `improve/adaptive-academic-depth` sobre `main@7c3a87e`) y el
resultado se sincroniza al final a la carpeta de destino
(`/Users/danielmigueltejedor/Documents/Proyecto predeterminado`), que **no es un
repositorio git** (copia plana sin `.git`).

El libro se regenera **sin red y sin proveedor de IA**: los motores de
profundidad, longitud, planificación, derivaciones, completitud, cobertura y
consistencia son deterministas; la prosa es redacción original en español
respaldada por extractos realmente recuperados.

## 3. Restricciones de integridad aplicadas

- **Solo se citan documentos realmente recuperados.** Las 21 fuentes se
  registraron por HTTP el 2026-10-09; los extractos son fragmentos verbatim
  cortos de las páginas recuperadas.
- **No se inventan fuentes, métricas, citas, certificados de verificación ni
  afirmaciones de éxito.** Toda cifra de este informe procede de ejecuciones
  reales (pytest, ruff, pyright, coverage, pdflatex, `pdftotext`).
- **La guía docente de la ULE solo se pudo recuperar como página pública del
  plan de estudios.** Por eso el libro se etiqueta como *libro general de
  Mecánica de Fluidos* y no como material oficial de la asignatura.
- **Sin pasajes extensos protegidos por derechos de autor:** citas de una o dos
  frases; el resto es redacción original.
- **No se debilita ninguna prueba** para hacer pasar el trabajo; se corrigieron
  defectos reales del motor de LaTeX (ver §12) y se añadieron pruebas de
  regresión.
- **No se rellena longitud con paja:** la ampliación de cada capítulo responde a
  carencias reales de completitud (definición, autoexamen, profundidad
  explicativa, dificultad de ejercicios y derivaciones), no a un objetivo
  cosmético de páginas.
- **Se preservan las distinciones de estado de verificación**
  (`COMPUTATION_REPRODUCED`, `SYMBOLICALLY_VERIFIED`, `DIMENSIONALLY_VERIFIED`,
  `INDEPENDENTLY_VERIFIED`, `TWO_WITNESSES`). `ACADEMICALLY_REVIEWED` es de nivel
  de auditoría y **no lo asigna nunca este pipeline**.
- **Sin bump a 1.0, sin merge, sin release, sin tag, sin force push.** Se
  mantiene la compatibilidad de registros y del pipeline público.

## 4. Las 18 partes

### Parte 1 — Verificación independiente de la iteración previa

Se comprobó la iteración anterior antes de tocarla: `pytest -q` = 247 aprobadas,
`ruff check src tests` limpio, `pyright` = 0 errores y cobertura fresca = 76,95 %
(la lectura obsoleta mostraba 72 % por un `.coverage` antiguo). Confirmada la
coherencia de registros y de contratos antes de empezar.

### Partes 2–3 — Motor de profundidad académica adaptativa

Nuevo paquete `src/studium/authoring/depth/`:

- `profiles.py`: perfiles de profundidad (aquí `ADVANCED_UNDERGRADUATE`) y de
  extensión (aquí `COMPREHENSIVE`), con páginas esperadas por concepto.
- `length.py`: estimador de longitud por concepto con **suelo = 0,75×** y
  **techo = 1,35×**; un objetivo incoherente genera una **nota explicativa**, no
  una aceptación silenciosa.
- `planner.py`: plan de profundidad determinista (conceptos, páginas objetivo,
  notas).

Herramientas: `studium_depth_plan`, `studium_depth_plan_status`.

### Parte 4 — Planificación jerárquica (blueprint académico)

`src/studium/authoring/academic_blueprint.py`: relaciona capítulos con
**conceptos** académicos e hitos de dominio; alimenta la cobertura y los
objetivos de aprendizaje de los ejercicios. Nuevo registro `ACADEMIC_BLUEPRINT`.
Herramientas: `studium_academic_blueprint_store`, `studium_academic_blueprint_get`.
El almacén rechaza un concepto cuyo id coincida con el de su capítulo.

### Parte 5 — Expansión iterativa de capítulos

`src/studium/authoring/expansion.py` detecta huecos de contenido por concepto y
planifica su expansión. Herramienta: `studium_expansion_plan`
(informa de `concept_gaps`). La escritura de párrafos se extendió con el campo
`concepts` para vincular cada párrafo a los conceptos del blueprint.

### Parte 6 — Completitud pedagógica

`src/studium/authoring/completeness.py` evalúa, por capítulo, la presencia de:
párrafo guía, ≥2 párrafos explicativos citados, profundidad (≈400 palabras),
**definición**, **autoexamen**, problema resuelto, ejercicios en ≥2 niveles de
dificultad, derivación con 0 sin verificar, y **notación/terminología**.
Herramienta: `studium_section_completeness`.
Registros y herramientas: `studium_notation_record` / `studium_notation_list`,
`studium_terminology_record` / `studium_terminology_list`.

### Parte 7 — Motor de derivaciones matemáticas

`src/studium/authoring/derivations.py`: registra derivaciones con supuestos,
principios, pasos, variables y límites, y las comprueba en tres frentes —
simbólico, numérico y dimensional—. Combina los resultados en un estado:
`INDEPENDENTLY_VERIFIED` (simbólico + numérico + dimensional),
`SYMBOLICALLY_VERIFIED`, `DIMENSIONALLY_VERIFIED`, `COMPUTATION_REPRODUCED` o
`FAILED`. Nuevo registro `DERIVATIONS`.
Herramientas: `studium_derivation_record`, `studium_derivation_check`,
`studium_derivation_list`.

### Parte 8 — Ejercicios mejorados

`src/studium/authoring/problems.py` se amplió con `role` (`worked`/`practice`),
`difficulty` (`FOUNDATIONAL`, `INTERMEDIATE`, `ADVANCED`, `EXAM_LEVEL`),
`learning_objectives` (referencian conceptos del blueprint) y `method`. El libro
incluye ahora **problemas resueltos y de práctica con dificultad creciente**, y
un apéndice de soluciones con la respuesta esperada de cada ejercicio.

### Parte 9 — Cobertura de fuentes

`src/studium/authoring/coverage.py` mide uso de fuentes y cobertura de conceptos.
Herramienta: `studium_source_coverage`.

### Parte 10 — Consistencia global del libro

`src/studium/authoring/consistency.py` revisa notación y terminología entre
capítulos en busca de definiciones divergentes. Herramienta:
`studium_consistency_report` (informa de `findings` y `consistent`).

### Parte 11 — Fiabilidad en ejecuciones largas

`src/studium/authoring/context.py` permite reanudar el trabajo: paquete de
reanudación y contexto de sección deterministas.
Herramientas: `studium_resume_packet`, `studium_section_context`.

### Parte 12 — Diseño LaTeX profesional

`src/studium/authoring/render.py`:

- Preámbulo con `\usepackage[hyphens]{url}`, `\usepackage[hidelinks]{hyperref}`
  y `\setlength{\emergencystretch}{1.5em}` (elimina las cajas *overfull*).
- Bibliografía con `\url{}`.
- **Apéndice de Notación** autogenerado y **Hoja de fórmulas**.
- **Cajas de derivación y de ejercicios** por capítulo.
- **Apéndice de soluciones** que numera los ejercicios de práctica y añade
  `Respuesta: <esperado>`.
- Se corrigió un **defecto real**: un comando griego seguido de una letra se
  concatenaba sin separador (`Δp` → `\Deltap`, comando inexistente). Ahora se
  inserta un separador (`\Delta p`) tanto en `_formula_tex` como en
  `_math_chars`. Se añadió una prueba de regresión en `tests/test_draft_book.py`.

### Parte 13 — Rendimiento

Los motores (profundidad, longitud, planificación, completitud, cobertura,
consistencia, derivaciones) son de coste lineal sobre los registros y se ejecutan
en el mismo pipeline offline; no añaden llamadas de red ni de modelo.

### Parte 14 — Pruebas y puertas de calidad

- `tests/test_academic_depth.py`: 11 pruebas nuevas para los motores y su
  integración con el render.
- Prueba de regresión del renderizado de letras griegas.
- `tests/test_public_bibliography.py` **no se debilitó**: se conserva la garantía
  de que los nombres públicos de herramientas no contienen «chapter» ni «pdf»;
  por eso las herramientas se llaman `studium_section_completeness` y
  `studium_section_context` (los nombres de función Python no cambian).
- Puertas finales: **259 pruebas**, ruff limpio, pyright 0 errores, cobertura
  76,48 %.

### Parte 15 — Regeneración del libro de Mecánica de Fluidos (ULE)

`examples/build-fluid-mechanics-ule.py` se reescribió por completo como
construcción offline determinista de un libro de **10 capítulos**:

1. Introducción a la mecánica de fluidos
2. Propiedades de los fluidos
3. Estática de fluidos
4. Ecuación de continuidad
5. Ecuación de Bernoulli
6. Teorema del transporte de Reynolds y cantidad de movimiento
7. Número de Reynolds y similitud
8. Flujo en tuberías
9. Capa límite
10. Instrumentación de medida

Cada capítulo incluye 2 párrafos explicativos base + definición + autoexamen +
párrafos explicativos adicionales según la carencia real detectada, un problema
resuelto con comprobación aritmética reproducida, ejercicios de práctica en ≥2
niveles de dificultad y, cuando aplica, una derivación. El libro registra **21
fuentes**, **56 párrafos**, **30 problemas** y **10 derivaciones**.

### Parte 16 — Informe de calidad basado en métricas

El propio pipeline genera `examples/fluid-mechanics-ule/QUALITY.md` a partir de
los registros almacenados y del PDF compilado. Contiene las métricas reales,
los estados de verificación de las derivaciones, la completitud por capítulo y
los límites del trabajo. No reclama revisión académica.

### Parte 17 — Validación

- `pdftotext -layout` extrae el texto; se comprobaron las secciones clave
  (Notación, Símbolo, Hoja de fórmulas, Derivaciones, Ejercicios, Respuesta) y la
  ausencia de fugas al inglés.
- `draft.log`: **0 errores (`!`)**, **0 cajas *overfull***.
- Cabecera del PDF `%PDF-` verificada; 38 páginas medidas.
- Auditoría: `studium_contradiction_scan` con 0 abiertas y `studium_book_review`
  con `audit_passed = True` y `released = False`.

### Parte 18 — Entrega

- Todo el trabajo permanece en la rama `improve/adaptive-academic-depth`,
  **sin fusionar**.
- El árbol se sincroniza a la carpeta de destino como copia plana (sin `.git`).
- Este informe resume el estado entregado.

## 5. Métricas medidas del libro regenerado

| Métrica | Valor |
| --- | --- |
| Capítulos (secciones) | 10 |
| Capítulos con prosa | 10 |
| Capítulos completos (contrato pedagógico) | 10 de 10 |
| Párrafos | 56 |
| Párrafos auditados | 56 |
| Palabras | 4 403 |
| Fuentes registradas / usadas | 21 / 21 |
| Conceptos planificados / cubiertos | 20 / 20 |
| Problemas / con resultado vigente | 30 / 30 |
| Comprobaciones aritméticas reproducidas | 10 |
| Derivaciones | 10 |
| Entradas de notación | 23 |
| Términos de glosario | 14 |
| Contradicciones abiertas | 0 |
| Consistencia entre capítulos | sí |
| Páginas medidas del PDF | 38 |
| Errores de LaTeX (`!`) | 0 |
| Cajas *overfull* | 0 |

Estados de verificación de las derivaciones: **8**
`INDEPENDENTLY_VERIFIED` y **2** `DIMENSIONALLY_VERIFIED`. Estos estados los
asigna el motor determinista; no equivalen a una demostración formal ni a una
revisión humana.

## 6. Herramientas MCP añadidas (18)

`studium_academic_blueprint_store`, `studium_academic_blueprint_get`,
`studium_depth_plan`, `studium_depth_plan_status`, `studium_expansion_plan`,
`studium_section_completeness`, `studium_section_context`,
`studium_derivation_record`, `studium_derivation_check`,
`studium_derivation_list`, `studium_notation_record`, `studium_notation_list`,
`studium_terminology_record`, `studium_terminology_list`,
`studium_source_coverage`, `studium_consistency_report`, `studium_quality_report`,
`studium_resume_packet`.

Nuevos registros en `src/studium/storage/records.py`:
`ACADEMIC_BLUEPRINT`, `DEPTH_PLANS`, `DERIVATIONS`, `NOTATION`, `TERMINOLOGY`.

## 7. Limitaciones y trabajo pendiente honesto

- **Ninguna persona ha revisado esta edición.** No se reclama
  `ACADEMICALLY_REVIEWED`.
- El recuento de páginas de la estimación (36,5–65,7) es un cálculo del plan de
  profundidad; el único dato medido es el del PDF compilado (38 páginas). El
  libro es, por tanto, una **edición parcial** dentro del rango estimado, no una
  obra completa de nivel de manual publicado.
- La guía docente oficial de la ULE no pudo recuperarse íntegra (solo la página
  pública del plan). El libro se etiqueta como libro general de Mecánica de
  Fluidos, no como material oficial de la asignatura.
- Los estados `INDEPENDENTLY_VERIFIED` proceden de la combinación de
  comprobaciones simbólicas, numéricas y dimensionales del servidor; no
  constituyen una prueba matemática formal.
- Quedan ampliaciones posibles (más ejercicios de nivel `EXAM_LEVEL`, figuras
  originales —actualmente 0—, y más derivaciones) que requerirían trabajo
  adicional de autoría y revisión.

## 8. Reproducción

```sh
source venv/bin/activate
python -m pytest -q
ruff check src tests
pyright
python -m pytest -q --cov=studium --cov-fail-under=75
python examples/build-fluid-mechanics-ule.py
```

El último comando regenera el libro y el PDF de forma determinista, sin red y sin
modelos externos.
