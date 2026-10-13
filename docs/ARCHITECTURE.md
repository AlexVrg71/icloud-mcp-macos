# Arquitectura

```text
Cliente MCP local ── stdio ───────────────┐
Cliente remoto ── HTTPS + OAuth ── proxy ├── servidor Python
                                        ├── IMAP/SMTP: correo iCloud
                                        ├── CalDAV: calendarios
                                        ├── CardDAV: contactos + respaldos
                                        └── socket Unix privado ── app Swift/EventKit
                                                                    └── réplica macOS de Recordatorios
```

El repositorio conserva el paquete Python `icloud_mcp` y publica el nombre de distribución separado `icloud-mcp-macos`. El lanzador independiente construye el entorno desde una configuración explícita; evita heredar secretos, rutas o funciones de otra instalación.

El auxiliar usa SwiftPM: biblioteca pura `RemindersCore`, ejecutable `ICloudMCPReminders` y pruebas `RemindersCoreTests`. `build-app.sh` crea el bundle AppKit, declara el motivo de acceso y firma ad hoc. No se abre durante compilación/tests. La utilidad `scripts/keychain.swift` solo guarda credenciales en los dos servicios de esta edición mediante Security.framework; se compila por separado y no solicita EventKit.

Identidad pública `org.icloudmcp.macos.reminders`; datos `~/Library/Application Support/iCloud-MCP-macOS/data/eventkit`. Servidor y auxiliar comparten ese valor derivado del HOME del usuario. La ruta del socket tiene el límite Unix de macOS; el instalador rechaza rutas demasiado largas. No cambia permisos de carpetas de otra instalación.

EventKit vive en MainActor. IPC serializa lectura y mutaciones. Un archivo de bloqueo excluye otro auxiliar; cada solicitud tiene un tamaño acotado y el servidor tiene timeout sin reintento automático. El registro de operaciones guarda el estado pendiente antes de escribir y el resultado después. Un fallo entre ambos deja resultado incierto que requiere conciliación manual.

Los permisos no se conceden remotamente ni al arrancar. El usuario selecciona listas en la app y guarda sus identificadores de cuenta/lista; si cambian, se exige selección nueva. La sincronización de Apple y la entrega de avisos son externas a la confirmación del guardado local.

Las modificaciones respecto al upstream incluyen corrección de prefijos OAuth, respaldos vCard, hilos entre carpetas, adjuntos temporales, división de recurrencias con recuperación e iMIP con deduplicación. El resto del núcleo permanece para evitar una refactorización ajena a la publicación.
