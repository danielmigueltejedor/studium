# Soluciones para comparar procedimientos

Un problema resuelto debe permitir localizar el primer paso en que el intento
del lector se separa de la solución. Un listado de fórmulas o una sustitución
final no cumple ese objetivo.

Para cada ejercicio numérico, el autor debe registrar:

1. Datos convertidos, incógnitas, ejes, signos y condiciones iniciales.
2. `solution.development`: por qué se elige el balance o ley, qué hipótesis lo
   permiten, cómo se despeja y en qué orden se necesitan las incógnitas.
3. `solution.steps`: una operación por paso, con `text` que explique la decisión,
   `equation` o `symbolic` para el álgebra, `expression` para la sustitución
   reproducible y `unit`. Conservar resultados intermedios sin redondearlos.
4. Respuesta a todos los apartados, interpretación y contraste por otra vía o
   sustitución en las ecuaciones iniciales. Explicar métodos alternativos válidos.

El renderizador conserva el desarrollo aunque no haya figuras y evalúa cada
expresión impresa para mostrar su resultado intermedio. No copia `expected`
como si fuese un cálculo: una discrepancia sigue apareciendo en la verificación.
Esto facilita comprobar la aritmética, pero no demuestra la elección del modelo
ni la suficiencia didáctica de un texto. Esas dos cuestiones requieren lectura
y revisión del ejercicio completo.

Ejemplo: con fuerza neta constante y reposo inicial, justificar `F=ma`, despejar
`a=F/m`, integrar para obtener `v=at`, despejar `t=V/a`, integrar de nuevo para
obtener `s=at²/2` y contrastar con `Fs=mV²/2`. La ruta directa de energía también
es válida para la distancia, pero no sustituye al desarrollo de aceleración y
tiempo cuando el enunciado los pide.
