# iCloud MCP Reminders: EventKit

macOS 14+, SwiftPM 5.9+, sin dependencias Swift externas. Productos: ejecutable `ICloudMCPReminders`, biblioteca `RemindersCore` y sus pruebas.

```sh
swift test
./build-app.sh
```

La app compilada está en `build/iCloud MCP Reminders.app`. Es una compilación de desarrollo con firma ad hoc `org.icloudmcp.macos.reminders`, sin notarización; compilar no la ejecuta. `--self-check` del ejecutable solo verifica el protocolo sin crear EKEventStore, pedir permiso ni abrir socket. No se debe ejecutar la app real durante CI.

El proceso se integra mediante el instalador descrito en el [README principal](../README.md). Datos: `~/Library/Application Support/iCloud-MCP-macOS/data/eventkit`. Socket privado, mismo UID, MainActor, solicitudes serializadas y recibos duraderos. Ver [arquitectura](../docs/ARCHITECTURE.md) y [seguridad](../SECURITY.md).

Herramientas:

| Nombre | Uso |
| --- | --- |
| `reminders_get_status` | Conexión y permiso sin solicitarlos. |
| `reminders_list_lists` | Lista/cuenta, clasificación, privacidad declarada y escritura. |
| `reminders_list_reminders` | Buscar pendientes/completados, paginar explícitamente. |
| `reminders_get_reminder` | Leer un elemento y su versión. |
| `reminders_create_reminder` | Lista explícita, UUID, confirmación, título y aviso explícito. |
| `reminders_update_reminder` | Cambios puntuales con versión; cambio de fecha requiere elegir aviso. |
| `reminders_complete_reminder` | Establecer completado/pendiente, no alternar a ciegas. |
| `reminders_delete_reminder` | Eliminar exactamente uno con instrucción explícita y versión. |

Las fechas con hora requieren zona IANA. Se rechazan horas ambiguas/inexistentes por cambios de horario. Fecha sin hora no inventa un aviso. No se modifican recurrencias, listas, subtareas, etiquetas o adjuntos.

Los controles de privacidad son locales y declarados por el propietario; no se debe describir una cuenta con nombre “iCloud” como verificada sin esa confirmación. Se puede leer lo accesible a EventKit, pero solo escribir listas confirmadas como iCloud. Desconocidas/compartidas/delegadas requieren permiso de visibilidad para colaboradores. Nunca conceder TCC desde una herramienta MCP.

`local_saved` no acredita sincronización o notificación. Los tres campos `sync_status`, `iphone_notification` y `watch_notification` permanecen `not_verified` desde el servidor; una confirmación humana de dispositivos se documenta por separado.
