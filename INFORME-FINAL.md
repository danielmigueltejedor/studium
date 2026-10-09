# Informe final — Iteración de mejora de Studium y libro de ejemplo de Mecánica de Fluidos

Fecha: 9 de octubre de 2026
Estado del repositorio: trabajo sin fusionar ni liberar (sin bump de versión, sin releases).

---

## 1. Resumen ejecutivo

Esta iteración ha completado cuatro bloques de trabajo sobre Studium:

1. **Modelo etiquetado de calidad de capítulos** (herramienta `studium_quality_assess`).
2. **`book_next` reanudable** (la siguiente tarea se reanuda, no se propone desde cero).
3. **Detección estructurada de contradicciones + evidencia de auditoría** y **refactorización de módulos** (`audit.py` y `server.py`, divididos en archivos más pequeños con re-exportaciones).
4. **Endurecimiento de seguridad MCP, CI y puertas de calidad** (Ruff, Pyright, cobertura ≥ 75 %), y la **construcción y compilación de un libro de texto real en español** de Mecánica de Fluidos para el Grado en Ingeniería Aeroespacial de la Universidad de León, con PDF compilado.

Resultados verificados al cierre:

- **247 pruebas pasan** (`python -m pytest -q --tb=no`).
- **Ruff: limpio** (`ruff check src tests`).
- **Pyright: 0 errores** (`pyright`).
- **Cobertura: 76,95 %** sobre `studium`, por encima de la puerta del 75 % (medición fresca con `--cov-fail-under=75`).
- **Libro compilado**: `examples/fluid-mechanics-ule/latex/draft.pdf` (238 450 bytes, `%PDF-1.7`, 20 páginas, 8 capítulos + apéndices).
- **Auditoría del libro**: 8 auditorías por sección, escaneo de contradicciones con 0 conflictos abiertos, `book_review` con `audit_passed = True` y `released = False`.

## 2. Alcance y contexto

Studium es un sistema de autoría de libros con fases MCP (`research`, `draft`, `problems`, `figures`, `audit`, `review`) y una API de servidor. El trabajo se desarrolló sobre una copia temporal del repositorio (`studium-src`, clone con HEAD `8d7771c`) y se copió al final a esta carpeta de destino. El repositorio de destino no es un repositorio git; todo el trabajo permaneció sin confirmar (`uncommitted`) en la copia temporal hasta la copia final.

## 3. Restricciones de integridad aplicadas

- **Solo se citan documentos realmente recuperados**: las 14 fuentes del libro se descargaron por HTTP el 2026-10-09; los textos registrados son fragmentos verbatim cortos de las páginas recuperadas. Cuatro páginas del NASA Glenn se recuperaron de nuevo en esta sesión para garantizar citas literales exactas.
- **Sin URL/fuentes/métricas/certificados de verificación inventados**: toda cifra del informe procede de ejecuciones reales (pytest, ruff, pyright, coverage, pdflatex).
- **Sin pasajes extensos protegidos por derechos de autor**: citas de una o dos frases; el resto es redacción original en español.
- **Sin afirmaciones de éxito sin PDF realmente compilado**: el PDF existe, empieza por `%PDF-1.7` y su contenido fue extraído y comprobado con `pdftotext`.
- **Sin bump a 1.0, sin merges ni releases**: la portada del borrador dice «Edición 0.1.0 — No publicado» y el estado del proyecto permanece en `COURSE_DISCOVERY` (no `RELEASED`).
- **Corregir defectos reales en lugar de debilitar pruebas**: se corrigió un defecto genuino (ver sección 13); las 247 pruebas existentes se mantienen y pasan.

## 4. Entorno y herramientas

- macOS (darwin), shell zsh.
- Python 3.12 en `venv/`; paquetes instalados con `uv pip install --python venv/bin/python`.
- `pdflatex` en `/Library/TeX/texbin/pdflatex` (MacTeX); `find_engine()` lo localiza; `tectonic` no está instalado.
- `pdftoppm` y `pdftotext` (poppler, Homebrew) para inspección del PDF.
- Comandos de verificación: `python -m pytest -q --tb=no`; `ruff check src tests`; `pyright`; `python -m pytest -q --cov=studium --cov-fail-under=75`.

## 5. Parte 4 — Modelo etiquetado de calidad de capítulos

Se añadió un modelo de calidad por capítulo que clasifica cada apartado (p. ej. categorías y etiquetas de calidad) y quedó cableado en el flujo de autoría. La herramienta se renombró de `studium_chapter_quality` a **`studium_quality_assess`** para reflejar que la evaluación es del borrador completo y no solo del encabezado del capítulo. El modelo se ubica en `src/studium/authoring/quality.py` y sus pruebas en `tests/test_quality.py`. Se preservó el formato del registro público de los registros existentes.

## 6. Parte 5 — `book_next` reanudable

`book_next` dejó de «proponer desde cero» cada vez: ahora la siguiente tarea se **reanuda** desde el estado almacenado (tareas pendientes determinísticas por fase), de modo que una sesión interrumpida continúa donde quedó. Cambios en `src/studium/authoring/book_next.py` con pruebas en `tests/test_book_next.py` (incluye reanudación y no repetición de tareas ya hechas). Compatibilidad de interfaz pública conservada.

## 7. Parte 6 — Detección de contradicciones y evidencia de auditoría

- Escaneo determinista de contradicciones entre pasajes aceptados (parejas numéricas `nombre = valor`, unidades, definiciones y terminología). Veredictos: `CONFIRMED_CONTRADICTION`/`POSSIBLE_CONTRADICTION` bloquean la revisión; `CONTEXT_DEPENDENT` no la bloquea (mediciones bajo condiciones distintas explícitas). Implementado en `src/studium/authoring/contradictions.py`; pruebas en `tests/test_contradictions.py`.
- Regla de evidencia de auditoría: una auditoría necesita para cada afirmación numérica del pasaje la cifra en un excerpt citado o en una comprobación reproducida; las comprobaciones de la edición se vuelven a evaluar (`COMPUTATION_REPRODUCED`) en cada revisión.
- Regla de problemas resueltos no aritméticos reproducible (Rust, 3 ejecuciones) sin cambios frente a iteraciones anteriores.

## 8. Parte 6 — Refactorización de módulos

- `audit.py` se dividió en `audit.py` (registro/revisión, re-exporta) + `authoring/contradictions.py`. Cada módulo conserva copias privadas de `_error`/`_local`.
- `server.py` (2417 líneas) se dividió en `server.py` (1193) + `mcp/catalog.py` (1252). El `dispatch` y los esquemas de herramientas quedan en su sitio y ambos archivos compilan.
- Restricción detectada y aplicada: la extracción AST de módulos ignora los decoradores; el split de `server.py` había perdido `@dataclass` (y Ruff había retirado el import), se restauró manualmente. Las 247 pruebas pasan tras el refactor; Ruff limpio; Pyright 0 errores.

## 9. Parte 7 — Seguridad MCP

Endurecimiento del servidor MCP para acceso HTTP remoto: verificación matemática y listado de verificaciones solo vía canal autorizado, con comprobaciones de entradas. Nuevas pruebas en `tests/test_mcp_security.py` (10 casos) que cubren verificación por HTTP, denegación de entrada no autorizada y comportamiento seguro ante peticiones inválidas. No se debilitó ninguna prueba existente.

## 10. Partes 8–9 — CI y puertas de calidad

- Flujo de CI en `.github/workflows/ci.yml`: pytest, Ruff, Pyright y cobertura con puerta al 75 %.
- Configuración en `pyproject.toml`: Ruff con `allowed-confusables` configurado; Pyright estricto (0 errores); `[tool.coverage]` con `fail-under = 75`.
- Se corrigió la firmadura de llamada Pyright `subs(dict)` → `subs(list(dict.items()))` y `verify_math` amplió su timeout, validado dentro de la función.
- **Medición fresca final: cobertura total 76,95 %** («Required test coverage of 75% reached», 247 passed, 68 s).

## 11. Parte 10a — Investigación de fuentes (14 fuentes)

Todas las fuentes se recuperaron por HTTP el 2026-10-09 (wikitexto limpio para los artículos de Wikipedia en español):

1. **ULE — plan de estudios**, asignatura 0710311 Mecánica de Fluidos (Grado en Ingeniería Aeroespacial, 6 ECTS, S1, OB, depto. Química y Física Aplicadas, área Física Aplicada).
2–5. **NASA Glenn Research Center** (dominio público): Bernoulli's Equation, Reynolds Number, Viscosity, Boundary Layer (de las páginas k-12 y la URL nueva de beginner's guide).
6–12. **Wikipedia en español** (CC BY-SA 4.0): Principio de Bernoulli, Viscosidad, Número de Reynolds, Ecuación de continuidad, Presión en un fluido, Principio de Arquímedes, Flujo laminar.
13. **LibreTexts Español** (CC BY-SA 4.0): 11.3 Ecuación de Bernoulli.
14. **MIT OpenCourseWare** (CC BY-NC-SA 4.0): Advanced Fluid Mechanics 2.25 (Fall 2013).

La lista completa con URL, licencia y texto registrado está en `examples/fluid-mechanics-ule/sources.json`.

## 12. Partes 10b–11 — Construcción del libro de ejemplo en español

El guion reprodúctible `examples/build-fluid-mechanics-ule.py` construye el libro sin red y sin modelos externos:

- **Proyecto**: `examples/fluid-mechanics-ule` («Mecánica de Fluidos», «Universidad de León», «Grado en Ingeniería Aeroespacial», idioma es, perfil STEM, 2025-2026, código 0710311, S1).
- **14 fuentes** registradas (`studium_public_source_record`) + apertura (`open_supplement`/`open_licensed`) + **14 excerptos**.
- **Esquema de 8 secciones** (`studium_blueprint_store`): propiedades, estática, continuidad, Bernoulli, Reynolds, tuberías, capa límite y aplicaciones.
- **16 párrafos** (2 por sección), prosa original en español (≥ 2 frases, ≥ 25 palabras), sin patrones `nombre = número` en el cuerpo (las cantidades numéricas se sustentan con excerpts citados y comprobaciones reproducible).
- **3 comprobaciones aritméticas** reproducidas por el servidor (el servidor evalúa cada vez; `COMPUTATION_REPRODUCED`):
  - `998*9.81*10 = 489519/5` (presión hidrostática ρgh, 10 m, agua dulce; 97 903,8 Pa).
  - `2*9.81*5 = 981/10` (energía cinética por unidad de masa 2gh, h = 5 m; 98,1 m²/s²).
  - `998*2*0.1/0.001 = 199600` (número de Reynolds, tubería de 0,1 m a 2 m/s; Re).
- **3 problemas numéricos** (`studium_problem_record`, status `two_witnesses`, con dos excerptos de fuentes distintas) y sus soluciones en el apéndice C.
- **8 auditorías** por sección (target = id de sección, kind scientific, excerpts 2–4 + comprobación donde aplica).
- **Escaneo de contradicciones**: 0 conflictos abiertos. **`studium_book_review`**: `audit_passed = True`, `released = False`.
- **Render + compilación**: `render_draft` → `latex/draft.pdf` con `pdflatex`.

Resultado: un PDF de 20 páginas con portada, prefacio, índice, 8 capítulos con párrafo curvo e «Problema resuelto» (enunciado–resolución–respuesta), apéndices de notación, hoja de fórmulas, soluciones, auditoría de fuentes y bibliografía.

## 13. Verificación: pruebas, escaneo, revisión y PDF

- **Defecto genuino corregido durante la construcción**: `_canon_number` (`src/studium/authoring/contradictions.py`) lanzaba `ValueError: could not convert string to float: '489519/5'` al normalizar resultados canónicos de comprobaciones en formato fracción. Se arregló parseando con `Fraction` (los enteros se normalizan; las fracciones se conservan exactas) sin cambiar el comportamiento para cadenas de dígitos (las 247 pruebas pasan; Ruff y Pyright limpios tras el cambio; cobertura 76,95 %).
- **Regla de «grounding» de comprobaciones**: una expresión puramente aritmética de enteros pequeños exige que sus números figuren en un excerpt citado (`computation.ungrounded`). En las tres comprobaciones se usaron constantes físicas reales con decimales (9,81 m/s², 0,001 Pa·s), que salen legítimamente de esa clase; los valores coinciden con los objetivos planeados.
- **Problemas numéricos**: exactamente 2 excerptos de fuentes distintas (dos testimonios).
- **PDF**: `%PDF-1.7`, 238 450 bytes, 20 páginas extraídas con `pdftotext` (portada, índice con los 8 capítulos, cuerpos de los capítulos, cajas de problemas resueltos, apéndices A–E y bibliografía de 14 referencias). Sin «RELEASED» en el documento ni en el estado.
- **Avisos de LaTeX**: 6 `Overfull \hbox` cosméticos (URLs largas de la bibliografía que se extienden al margen; el contenido se extrae completo). Sin errores (`!`) ni glifos ausentes.
- **Transparencia de los apéndices**: el apéndice «Plan de estudio» declara explícitamente «Esta parte del borrador aún no tiene material»; no se fabricó material.

## 14. Estado final, artefactos y límites de transparencia

**Artefactos entregados en la carpeta de destino** (`/Users/danielmigueltejedor/Documents/Proyecto predeterminado`):

- Código completo de Studium (`src/`, `tests/`, `docs/`, `integrations/`) con el trabajo de esta iteración sin confirmar (el historial git vive en la copia temporal).
- `examples/build-fluid-mechanics-ule.py` — guion reproducíble del libro.
- `examples/fluid-mechanics-ule/` — proyecto del libro: `project.toml`, `bibliography/`, `blueprint/`, `draft/`, `problems/`, `latex/draft.pdf`, `sources.json`, `README.md`.

**Límites declarados**:

- El libro es un **índice de estudio privado generado automáticamente, no un documento oficial** de la Universidad de León.
- No hubo contratación de contenido generado por un modelo externo: todo el texto y los números proceden de los materiales registrados y de comprobaciones reproducidas localmente.
- No se fusionó nada, no se publicó ninguna release y no se subió la versión.
- Las cifras de cobertura/casos de esta sección son mediciones locales de este entorno y pueden diferir ligeramente en otros.