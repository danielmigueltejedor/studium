# Informe de calidad — Mecánica de Fluidos (ULE)

Generado por el propio pipeline a partir de los registros almacenados y del PDF
compilado. No se inventan cifras: todas proceden de `studium_quality_report`,
`studium_section_completeness` y del registro de LaTeX.

## Métricas del libro

| Métrica | Valor |
| --- | --- |
| Capítulos (secciones del esquema) | 10 |
| Capítulos con prosa | 10 |
| Capítulos completos (contrato pedagógico) | 10 de 10 |
| Párrafos | 56 |
| Párrafos auditados | 56 |
| Palabras | 4403 |
| Fuentes registradas | 21 |
| Extractos usados | 21 |
| Problemas | 30 |
| Problemas con resultado vigente | 30 |
| Comprobaciones aritméticas reproducidas | 10 |
| Derivaciones | 10 |
| Entradas de notación | 23 |
| Términos de glosario | 14 |
| Cobertura de fuentes | 21 de 21 |
| Cobertura de conceptos | 20 de 20 |
| Consistencia entre capítulos | sí |
| Contradicciones abiertas | 0 |
| Páginas medidas del PDF | 48 |
| Páginas planificadas (rango) | 36–66 |
| Veredicto de longitud | WITHIN_RANGE |
| Errores de LaTeX (`!`) | 0 |
| Cajas overfull | 0 |

## Longitud medida frente al plan

El plan de profundidad declara un ámbito COMPREHENSIVE de 36–66 páginas. El PDF medido tiene 48 páginas y el veredicto automático de longitud es WITHIN_RANGE.

## Estados de verificación de las derivaciones

- DIMENSIONALLY_VERIFIED: 2
- INDEPENDENTLY_VERIFIED: 8

Estos estados los asigna el motor determinista de verificación. No incluyen un
juicio académico humano: la edición no reclama ACADEMICALLY_REVIEWED.

## Completitud pedagógica por capítulo

| Capítulo | Completo | Falta |
| --- | --- | --- |
| introduccion | sí | — |
| propiedades | sí | — |
| estatica | sí | — |
| continuidad | sí | — |
| bernoulli | sí | — |
| momentum | sí | — |
| reynolds | sí | — |
| tuberias | sí | — |
| capa-limite | sí | — |
| instrumentacion | sí | — |

## Alcance y límites

- no human instructor has reviewed this edition; ACADEMICALLY_REVIEWED is not claimed by this pipeline
- page targets are estimates (36.5–65.7); only the compiled PDF's page count is a measured fact
- El recuento de páginas de la estimación es un cálculo del plan de profundidad;
  el número medido es el del PDF compilado que figura en la tabla anterior.
- Las derivaciones se comprueban de forma simbólica, numérica y dimensional por el
  propio servidor; eso no constituye una demostración formal ni una revisión humana.
