# Studium · aplicación de estudio

Cliente web en español del framework Studium: apuntes, libros académicos en
borrador, tarjetas con repaso espaciado, podcasts, calendario y comunidad pública
con publicación voluntaria. Node 24+; Python 3.11+ para regenerar los módulos.

```sh
npm ci
npm test
npm run build
npm run validate
npm run dev
```

La vista previa usa http://127.0.0.1:4173. `STUDIUM_PREVIEW_PORT` cambia el puerto.
Sin DB/R2 se mantiene la biblioteca local. `STUDIUM_LOCAL_ACCOUNTS=1` activa un
entorno de desarrollo efímero con SQLite real y un adaptador de objetos en memoria,
solo en loopback. Sus cuentas y objetos se pierden al detenerlo; nunca usar sus
claves de prueba en producción.

## Framework y contenido

`public/studium-core.js` contiene 118 módulos Python originales de la revisión
`f7bc7310507b83bb23738511843fc7c7f1b6c96e`, con huellas por archivo. Se ejecutan
mediante Pyodide 0.29.3, SymPy y Pint 0.25 en un Worker. El adaptador crea el proyecto,
registra fuentes versionadas, jerarquía y profundidad, localiza citas exactas y
registra párrafos pendientes. Los proyectos completos, informes y borradores TeX
se pueden exportar. Ningún flujo web marca un material como publicación académica
liberada: no hay compilador TeX ni hilos Python, y la revisión semántica/experta
permanece pendiente. La presencia de una cita no prueba el respaldo de una afirmación.

Apuntes, resúmenes y libros recorren todos los bloques del texto completo. Las
tarjetas usan una selección repartida de bloques según la cantidad solicitada;
no prometen cubrir todo un manual con seis tarjetas. Cada bloque se guarda para
reanudar tras cuota, desconexión o cancelación. Un libro es siempre un borrador.
Los podcasts seleccionan identificadores de fragmentos precalculados: la app
recupera la cita exacta y sus offsets del texto original del PDF, sin pedir al
modelo que la transcriba. Los identificadores ajenos al bloque se rechazan. Si el modelo inserta códigos de
citas en el diálogo, se trasladan a las evidencias antes de comprobar las cifras
y crear el audio; los valores numéricos sin respaldo siguen rechazándose. Las
respuestas antiguas con citas literales conservan compatibilidad y se restituyen
a su fragmento original; no se aceptan paráfrasis como citas.

La planificación de audio distingue contenido técnico, presentaciones e índices;
los puntos de un índice no cuentan como palabras explicativas. El objetivo de
extensión es orientativo: una diferencia de hasta el 2,5 % del mínimo (máximo
24 palabras) se registra como `NEAR_PLANNED_SCOPE`, con recuento real y sin relleno.
La cobertura de la fuente, las citas, los números y los personajes siguen siendo
obligatorios. Los bloques claramente insuficientes se conservan aparte como
borradores incompletos y se amplían con intervenciones nuevas, sin reescribir el
avance: hasta ocho ampliaciones por ejecución, con reintentos de formato acotados. Si una respuesta mezcla intervenciones repetidas y nuevas, conserva solo las nuevas y vuelve a comprobar sus evidencias.
La cuota o un fallo temporal del framework no descartan el texto ya validado.
Los manuales extensos se distribuyen en partes de hasta 40 capítulos, respetando
la estructura del núcleo original sin omitir bloques. La preparación comprueba
el resultado del esquema, la estructura académica y el plan antes de generar.
Al reanudar un proyecto del adaptador anterior, se reconstruye su estructura y
se vuelven a registrar las intervenciones conservadas sin regenerar el guion.
Cada intervención registra todas sus citas; un rechazo identifica bloque,
intervención y motivo del framework. Las revisiones semántica y experta siguen
pendientes, aunque las citas se hayan localizado.
El registro nativo y la revisión del guion solo avanzan al completar las
comprobaciones; ninguna tolerancia de audio libera una publicación académica.

Los cuadernos y fuentes personales se registran en segundo plano tras una pausa,
sin detener la tinta. Los trazos se conservan como geometría: no se afirma OCR.

Para regenerar el núcleo desde este monorepo:

```sh
python scripts/build-studium-core.py
```

En un checkout independiente, usar `--source /ruta/studium/src/studium`. La copia
ligera de planificación de podcasts tiene un adaptador JS identificado si no carga
Python; la creación con el núcleo completo falla de forma visible si no puede
cargarlo y conserva el avance. La primera carga necesita red y memoria disponible.

## Estudiar y organizar

- Cuadernos con tinta incremental, presión, selección, fórmulas LaTeX y figuras.
  Guardado de páginas en un Worker. PDFs originales renderizados por página con
  gráficos y ecuaciones, anotación y exportación visual; sin reconstrucción
  automática del LaTeX ni OCR inventado. El índice solo contiene vistas previas;
  los cuerpos, capítulos y archivos completos viven en IndexedDB.
- FSRS-7 real con `ts-fsrs@6.0.0`, cuatro grados, aprendizaje y reaprendizaje breve,
  fechas e historial persistentes. Práctica libre sin modificar el calendario.
- Podcasts con extensión según fuente y profundidad, bloques completos, citas,
  reanudación y control de cifras. Ana/Leo conservan dos IDs de voz y un modelo
  fijado; cada intervención se sintetiza por separado y se ensambla en WAV.
  Las pruebas de audio usan tonos, sin claves reales ni llamadas TTS facturadas.
- Calendarios manuales e ICS/enlaces HTTPS, recurrencias, excepciones y zonas
  horarias. Ventana de importación -31/+180 días, actualización manual de enlaces.
  Planificación con IA y asignación sin solapes, propuesta revisable antes de
  guardar. Avisos con la app abierta y exportación ICS con alarmas; sin push cerrado.
- Asignaturas con centro, carrera/ciclo/curso; comunidad pública con copias
  voluntarias, perfiles, filtros, me gusta, avisos y retirada por autor. El progreso
  privado de las tarjetas no se publica. No se comparte la biblioteca automáticamente.

## Cuentas, conexiones y almacenamiento

Registro propio con usuario/contraseña, foto, descripción y recuperación mediante
código mostrado una vez. scrypt N=16384/r=8/p=5 con pepper, salt individual y límites
de intentos. Sesiones de 30 días con cookie HttpOnly/Secure/SameSite y token hasheado.
El perfil público es voluntario. La identidad de ChatGPT sigue disponible para
la comunidad donde Sites inyecta encabezados verificados.

Diez proveedores: OpenRouter, Gemini, Groq, Cerebras, Hugging Face, OpenAI, Claude,
Mistral, DeepSeek y xAI. Catálogos consultados al proveedor; Claude usa Messages y
xAI Responses. OpenRouter ofrece inicio de sesión PKCE con estado ligado a la
sesión, de un uso y diez minutos. Los demás usan su API. No se usan cookies de
suscripciones de chat como acceso API. Big Pickle se retiró por no admitir este uso.
El modo gratuito bloquea los proveedores marcados de pago y las variantes de pago
de OpenRouter; los servicios con cuota dependen del plan/facturación del usuario.

Las claves de invitado permanecen en memoria. Al guardar una conexión en una
cuenta, se cifra con AES-GCM, IV aleatorio y propietario/finalidad como AAD. No se
retorna la clave ni se incluye en copias o publicaciones. La biblioteca está
separada por cuenta también en el navegador. Sincronización privada D1/R2 con
objetos SHA-256 por fragmentos, revisiones CAS, historial y fusión de cambios
independientes. Los conflictos conservan ambas versiones y requieren elección.
Los cambios remotos esperan a que cierres un cuaderno. El servidor limita a 2 GB
por cuenta; el original subido admite 25 MB por archivo. No se recorta el texto
extraído por un límite de caracteres.

Producción necesita dos secretos independientes de 32 bytes base64url:
`STUDIUM_PASSWORD_PEPPER` y `STUDIUM_VAULT_KEY`, gestionados por el alojamiento.
No rotarlos sin un plan de migración: protegen las contraseñas y conexiones
existentes. Nunca incluirlos en `.env` distribuido, Git, copias o manifiestos.

## iCloud y Apple Pencil Pro

`native-ios/` contiene el contenedor WKWebView para iPadOS 17.5+ con puente UIKit
de squeeze/doble toque y sincronización de carpeta elegida en Archivos. Usa
bookmarks por cuenta verificada con la cookie HttpOnly, coordinación de archivos,
objetos inmutables y CAS del índice. Es compatible con iCloud Drive y con otros
proveedores de Archivos que admitan carpetas. Guardado local no significa subida
confirmada; se detectan conflictos y se conserva el contenido. Los conflictos
nativos NSFileVersion se detienen para resolución externa; no hay selector de
versiones nativas en esta edición.

Safari solo permite importar/exportar copias por Archivos. No hay conexión web
persistente CloudKit, ni conectores web OAuth de Drive/OneDrive/Dropbox: requieren
registro y credenciales de cada servicio. La sincronización de la cuenta Studium
sí funciona desde la web. El código nativo necesita Xcode completo, firma e iPad;
no se ha compilado ni probado con Pencil/iCloud físicos en esta sesión.

## Publicación y licencias

Worker ESM con activos incrustados, D1 `DB`, R2 `BUCKET` y migraciones Drizzle
aplicadas durante el despliegue de Sites. `.openai/hosting.json` conserva el sitio.
No se crea esquema en peticiones. En otro alojamiento, sustituir la identidad
inyectada de Sites por verificación propia y eliminar encabezados de cliente.
Los enlaces ICS pueden contener tokens: son parte de la biblioteca privada y sus
copias/sincronización, nunca de una publicación comunitaria.

`npm run vendor` regenera dependencias fijadas y sus licencias. El núcleo original
y la marca proceden del framework bajo Apache-2.0. Los iconos de proveedores son
sus marcas de Simple Icons/Lobe Icons, sin afiliación. No se distribuyen datos de
usuarios, claves, materiales privados, dependencias, `work/` ni temporales.
