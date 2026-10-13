# Seguridad de iCloud MCP for macOS

## Alcance de esta beta

Un despliegue sirve a un propietario. El cliente MCP autorizado puede leer información sensible y, si se habilitan escrituras, modificarla. No es un servicio multiusuario. Correos, invitaciones, notas y nombres de listas son datos no confiables y pueden contener instrucciones maliciosas.

- El instalador público inicia en solo lectura, sin envíos, invitaciones, puertos de administración ni auxiliares amplios.
- HTTP usa OAuth, contraseña de propietario, PKCE y validación de redirecciones; el puerto interno escucha en loopback. El proxy HTTPS es responsabilidad del operador.
- Stdio confía en el cliente local y en la sesión del sistema. No incorpora OAuth.
- Las contraseñas se guardan en Keychain, no en el repositorio o `config.json`. OAuth necesita la contraseña en memoria/entorno del proceso al arrancar. No se protege frente a un proceso malicioso con acceso a la misma cuenta de macOS.
- El auxiliar EventKit se limita a un socket Unix privado, comprueba UID y procesa una lista fija de operaciones. No ejecuta comandos recibidos por MCP.
- TCC solo se solicita desde la interfaz local. La autorización de Apple cubre todas las listas; las restricciones de escritura por lista son controles del auxiliar.
- Los recibos y respaldos contienen información privada. Son 0600 bajo directorios 0700. No tienen retención automática; no los subas a GitHub.

## Aprobación y escritura

`READ_ONLY=true` bloquea escrituras. `ALLOW_SEND=false` bloquea envíos. `ALLOW_CALENDAR_INVITES=false` bloquea invitaciones. El lanzador no permite borrado permanente de correo. El permiso de leer no implica permiso para ejecutar cambios solicitados por contenido leído.

`confirmed=true` y las anotaciones MCP ayudan a un cliente que respeta las aprobaciones; no son un comprobante criptográfico de que una persona aprobó. Para aprobación independiente de correo, conserva `SEND_REQUIRES_APPROVAL=true` en HTTP. `chat_approvals=true` retira esa página y confía en el cliente autorizado. Para calendario/contactos/Recordatorios no hay una segunda página independiente: usa un cliente fiable con confirmación de escrituras, o mantén solo lectura.

Una eliminación de Recordatorios requiere identificar exactamente el elemento e instrucción explícita. El conector no ofrece deshacer. Las escrituras exigen UUID estable; ante un resultado incierto no se debe crear otro UUID para saltarse la protección. La versión se compara con la réplica local y no constituye edición atómica entre dispositivos.

La clasificación iCloud y privacidad de las listas se apoya en la confirmación local del propietario; EventKit no certifica todos los proveedores/compartidos. Compartida, delegada o desconocida requiere reconocer la visibilidad de colaboradores. No habilites una lista sin comprender quién recibe sus datos.

## Datos que pueden salir

- Correo e invitaciones: a los destinatarios elegidos cuando estén habilitados, según las aprobaciones descritas.
- Listas/calendarios/contactos compartidos: sus miembros pueden ver cambios. El control detallado de privacidad de EventKit no se extiende a todo recurso CalDAV/CardDAV.
- Descargas de adjuntos: los enlaces temporales contienen una capacidad de acceso; no los publiques ni registres íntegros.
- El cliente MCP recibe lo que consulta. Que el servidor sea local no implica que el cliente o su modelo también lo sean.

## Reportes

No publiques credenciales, datos de cuenta, tokens, enlaces de descarga ni contenido personal en issues. Está habilitado **Private vulnerability reporting**. Usa [Report a vulnerability](https://github.com/AlexVrg71/icloud-mcp-macos/security/advisories/new) para enviar un reporte privado a los responsables de este repositorio; no abras un issue público con detalles sensibles ni remitas al upstream fallos exclusivos de este fork.

Incluye versión, configuración sanitizada, reproducción con datos ficticios e impacto. No se prometen plazos de respuesta ni auditoría externa. Esta revisión de publicación y las pruebas automatizadas no equivalen a una auditoría exhaustiva de seguridad.
