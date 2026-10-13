# Operación de la edición pública

## Archivos y secretos

Todo el estado de esta edición vive bajo `~/Library/Application Support/iCloud-MCP-macOS`:

- `.venv/`, `manage.py`, `bin/`, `apps/`: programa instalado.
- `config.json`: configuración privada 0600 (cuenta, zona, URL, puerto y políticas); nunca contraseñas. Copia la estructura de `defaults()` si necesitas compararla. No agregues variables arbitrarias.
- `data/`: tokens OAuth, recibos de operaciones, respaldos vCard, recuperación de calendarios y adjuntos temporales. Puede contener datos personales completos. No subirlo a GitHub.
- `data/eventkit/`: socket 0600, identificación de listas y recibos duraderos de mutaciones. No borrar recibos pendientes para forzar un reintento.
- `logs/`: diagnósticos privados, no adjuntar sin revisión.

Keychain usa servicios `icloud-mcp-macos.apple` y `icloud-mcp-macos.oauth` con la cuenta configurada. Son elementos genéricos del llavero, consultables con Acceso a Llaveros. No se guardan en la app Contraseñas como credenciales de un sitio web. La utilidad nativa guarda el secreto recibido por stdin con Security.framework; no usa contraseña en argv ni un archivo temporal. El lanzador recupera OAuth sin imprimirlo y lo entrega al servidor en su entorno de proceso. El servidor lee la contraseña de Apple del Keychain. Esto no protege frente a malware ejecutándose con los permisos del propietario.

`python3 scripts/manage.py rotate-credentials` permite introducir sustitutos desde Terminal. No crea ni revoca contraseñas en Apple: hazlo en tu Apple Account. Para añadir HTTP a una configuración que era solo stdio, detén el servidor, añade tu `public_url` a `config.json`, ejecuta `rotate-credentials` para guardar también OAuth y arranca de nuevo. Cambiar la contraseña del propietario no invalida por sí solo todos los tokens OAuth ya emitidos.

Para revocar sesiones, detén el servidor y retira de forma privada `data/oauth_state.json` (perderás los clientes/tokens guardados); al arrancar será necesario reconectar. Antes verifica el archivo y conserva un respaldo si necesitas investigar un incidente. No copies tokens a issues.

## Arranque y parada

```sh
python3 scripts/manage.py start --helper  # habilita EventKit al iniciar sesión
python3 scripts/manage.py start           # habilita servidor HTTP al iniciar sesión
python3 scripts/manage.py stop            # detiene y retira solo el agente HTTP público
python3 scripts/manage.py stop --helper   # detiene y retira solo el agente EventKit público
```

Etiquetas: `org.icloudmcp.macos.server` y `org.icloudmcp.macos.reminders`. Si solo usas stdio, tu cliente gestiona el servidor; no ejecutes `start` HTTP. Usa un solo proceso de servidor de esta edición con escrituras para evitar carreras entre recibos/respaldos; varias conexiones remotas al mismo servidor sí son normales. El auxiliar impide que dos procesos abran el mismo socket.

Los scripts rechazan reemplazar destinos o agentes existentes. Un fallo de instalación puede dejar un directorio parcial sin servicios; inspecciónalo antes de moverlo o retirarlo. Un fallo de bootstrap puede dejar el archivo LaunchAgent; `stop` permite retirarlo tras comprobar que no está cargado. No se ofrece un borrado automático de datos o Keychain.

## Políticas y cambios de configuración

`read_only=true` omite herramientas de escritura. Para activar escrituras en una instalación configurada, detén servidor/clientes, edita el booleano a `false`, y reinicia/refresca el catálogo. `allow_send`, `allow_calendar_invites` y `chat_approvals` son opciones independientes. Mantén aprobación de cambios en el cliente; `chat_approvals=true` solo retira la segunda página de aprobación del correo, no autentica cada intención del usuario.

Las opciones heredadas que no aparecen en `config.json` no se heredan del entorno del shell. El lanzador deshabilita los auxiliares amplios y el API de administración. No añadas contraseñas a `config.json` ni habilites overrides con secretos en disco.

## Actualización y retirada

Esta beta **no tiene actualizador automático**. No reemplaces una instalación activa sobre la marcha. Conserva código/versión anterior y respaldo privado del directorio, detén clientes y ambos agentes, y prepara la siguiente versión por separado. El instalador no migra instalaciones anteriores; una actualización debe incluir instrucciones de migración revisadas. Sustituir una app firmada ad hoc puede exigir conceder de nuevo el permiso de Recordatorios. No resetees TCC ni desactives Gatekeeper para evitarlo.

Para retirar esta edición, primero detén clientes stdio y usa ambos comandos `stop`. Revoca el permiso de Recordatorios desde Ajustes del Sistema si lo deseas. Retira después la app, datos y entradas del Keychain de esta edición manualmente, solo tras decidir qué respaldos conservar. No elimines agentes ni rutas de otros servicios.

## Retención y recuperación

Los respaldos de contactos, manifiestos de división de calendario y recibos de Recordatorios no tienen limpieza automática. Pueden crecer y contienen datos privados. Respáldalos cifrados y define una retención manual. Eliminar recibos pierde protección frente a reintentos antiguos. Recuperar un respaldo requiere revisión; no hay restauración universal automática.

Ante un resultado incierto, lee/busca primero. No repitas una creación con otro `request_id`; conserva el UUID y argumentos originales. En un cambio recurrente CalDAV pueden existir dos recursos: la división no es atómica; consulta ambos antes de resolverla.
