# Changelog

## 0.1.0b1 — beta pública de código fuente

- Nombre independiente: iCloud MCP for macOS (`icloud-mcp-macos`), para clientes MCP con o sin Dot.
- Snapshot del fork de iCloud MCP 0.12.1 con correo, calendario, contactos y EventKit Reminders.
- Instalador macOS relativo al usuario, aislado de otros despliegues, sin activación automática.
- Credenciales en Keychain mediante utilidad Security.framework y stdin privado.
- Inicio en solo lectura; envíos, invitaciones, Recordatorios y aprobación exclusiva del chat requieren opciones explícitas.
- Documentación en español, límites de seguridad y procedimientos de mantenimiento/retirada.
- Pruebas sintéticas, workflow de CI sin secretos y comprobación de higiene para fuentes públicas.

Sin instalación limpia en otro Mac, sin notarización, sin publicación en PyPI ni pruebas nuevas sobre cuentas reales.
