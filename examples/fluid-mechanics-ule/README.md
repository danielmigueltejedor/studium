# Mecánica de Fluidos — libro de ejemplo (ULE, Grado en Ingeniería Aeroespacial)

Este directorio es un libro de ejemplo construido por el pipeline de autoría de
Studium, en español, para el plan de estudios de la asignatura **0710311
Mecánica de Fluidos** (6 ECTS, S1, obligatoria, Área de Física Aplicada) del
**Grado en Ingeniería Aeroespacial de la Universidad de León**.

**No es un documento oficial de la universidad.** Es un índice de estudio
privado generado automáticamente.

## Qué contiene

- `project.toml` — ficha del curso y perfil (STEM, es).
- `bibliography/` — las 21 fuentes públicas registradas y sus excerptos.
- `blueprint/` — el esquema (outline) con las 10 secciones y el plan de profundidad.
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
modelos externos: registra las fuentes, guarda el esquema de 10
secciones, escribe el plan de profundidad y el plan académico, redacta los
párrafos, reproduce las comprobaciones aritméticas (`expr = valor` lo vuelve a
evaluar el propio servidor), registra las derivaciones con sus comprobaciones
simbólicas, numéricas y dimensionales, los problemas trabajados y de práctica,
la notación y la terminología, audita cada sección, escanea contradicciones,
revisa la edición y compila `latex/draft.pdf` con LaTeX.

## Fuentes

Las 21 fuentes (URL y licencia en `sources.json`) se recuperaron el
2026-10-09. Los textos registrados son fragmentos verbatim cortos de esas
páginas: NASA Glenn (dominio público), Wikipedia en español (CC BY-SA 4.0),
LibreTexts Español (CC BY-SA 4.0) y MIT OpenCourseWare (CC BY-NC-SA 4.0). No
hay grandes pasajes protegidos por derechos de autor; las citas se limitan a
una o dos frases y el resto del texto es redacción original del libro.
