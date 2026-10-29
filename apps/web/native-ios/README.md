# Studium para iPad: puente de Apple Pencil

Contenedor WKWebView para iPadOS 17.5 o posterior. Usa las APIs reales de UIKit
para doble toque y squeeze de Apple Pencil Pro y respeta las preferencias del
sistema. Solo envía gestos al origen HTTPS exacto de Studium. En las pantallas de
inicio de sesión o cualquier otro dominio no se ejecuta el puente.

Safari y las aplicaciones web instaladas no exponen estos dos gestos nativos a
JavaScript. El editor web admite presión, inclinación, borrador y botones estándar
cuando el navegador los entrega, y ofrece paleta y cambio de herramienta en pantalla.
No intenta adivinar un doble toque a partir de trazos de escritura.

Para compilar: instalar Xcode completo y XcodeGen; ejecutar `xcodegen generate`
en esta carpeta, abrir Studium.xcodeproj, elegir equipo de firma e iPad y ejecutar.
Como alternativa, crear una app SwiftUI para iPad en Xcode (iPadOS 17.5) y añadir
los tres archivos Swift de Studium/.

No compilado ni probado en Apple Pencil físico en esta sesión: este Mac solo
dispone de Command Line Tools. La instalación y la firma necesitan Xcode y el
equipo de desarrollo del usuario. No es una app publicada en App Store.

APIs:
- https://developer.apple.com/documentation/uikit/uipencilinteractiondelegate
- https://developer.apple.com/videos/play/wwdc2024/10214/

## Carpeta de iCloud Drive

El tercer archivo Swift, StudiumCloudBridge.swift, implementa el puente de Archivos.
En «Mi cuenta», entra en una cuenta Studium y elige una carpeta. El permiso se
conserva mediante un bookmark propio de esa cuenta. Cada operación comprueba
origen, ventana principal y la sesión HttpOnly contra /api/account/me. Los archivos
están bajo Studium/<UUID de cuenta>, con nombres SHA-256 cerrados y límite de 8 MB
por fragmento. Los objetos son inmutables, el índice usa comparación de huella y
las escrituras son coordinadas y atómicas. Se conservan las versiones en conflicto;
esta edición detiene la sincronización si iCloud expone versiones nativas en
conflicto y requiere resolverlas externamente. No las sobrescribe en silencio.

iCloud controla su transferencia. Un «guardado en carpeta» no confirma la subida
de todos los objetos ni su recepción en otro dispositivo. La web en Safari solo
puede importar/exportar archivos; la carpeta persistente requiere este contenedor.
No se requieren credenciales de CloudKit para el acceso concedido desde Archivos.
Otros proveedores de Archivos funcionan si permiten seleccionar carpetas.
