# Conexión a ChatGPT, Claude y otros clientes MCP

El repositorio no crea un servicio en GitHub. El servidor debe ejecutarse en el Mac del propietario, con una dirección HTTPS estable accesible al cliente MCP. La configuración de DNS/túnel/proxy queda bajo control del operador: el instalador no cambia Tailscale, routers ni servicios existentes.

## Configuración inicial

Después de `install`, y antes del primer `configure`, prepara tu propio dominio/proxy. Ejemplo deliberadamente no operativo:

```sh
python3 scripts/manage.py configure --enable-reminders --public-url https://mcp.example.invalid --allow-writes
```

Sustituye el dominio por el tuyo. Añade `--allow-send` para correo saliente, `--allow-invites` para invitaciones y `--chat-approvals` si usarás únicamente la aprobación del cliente para los envíos. Sin `--allow-writes` el catálogo es de lectura. `configure` pide en Terminal la contraseña específica de Apple y una contraseña diferente de OAuth (12 caracteres como mínimo), ambas ocultas y confirmadas dos veces. No comprueba las credenciales ni publica el servicio.

```sh
python3 scripts/manage.py start --helper
python3 scripts/manage.py open-reminders
python3 scripts/manage.py start
```

`start` registra solo el LaunchAgent de esta edición. El servidor escucha en **127.0.0.1:8876** por defecto; usa `--port` durante `configure` si está ocupado. No expongas el socket de EventKit. No reenvíes puertos de administración o de auxiliares heredados.

## Requisitos del proxy

Para un dominio dedicado, reenvía su raíz HTTPS al servidor de loopback, preservando método, cuerpo y las cabeceras necesarias. El endpoint es `https://TU-DOMINIO/mcp`; el valor `public_url` es la base, sin `/mcp`.

Para un prefijo como `/icloud`, establece `public_url=https://TU-DOMINIO/icloud` y configura el proxy para **quitar ese prefijo** al reenviar. También debes enrutar el descubrimiento OAuth RFC 8414/RFC 9728 que solicite el cliente en `/.well-known/…` al servidor correcto. Las rutas exactas dependen del cliente y proxy; no sobrescribas el descubrimiento de otro servicio que ya use el dominio. Un subdominio dedicado evita esa colisión. El conjunto raíz/prefijo se prueba con transporte ASGI sintético, no con todos los proveedores de túnel.

TLS es obligatorio en el acceso remoto. No desactives la validación de certificados ni uses el puerto HTTP interno como endpoint de Internet. OAuth protege el MCP; las páginas de aprobación y registro son parte de ese flujo. Los enlaces temporales de adjuntos autorizan por posesión del enlace y deben tratarse como privados.

## Conectar el cliente

La conexión es al servidor MCP, independiente de Dot o de cualquier asistente personalizado. Puedes usarla desde una conversación normal o desde tu asistente preferido. Cada cliente decide cómo descubrir herramientas, presentar aprobaciones y permitir conexiones remotas; el servidor mantiene el mismo protocolo y límites de acceso.

Añade la URL `/mcp` como servidor MCP remoto y completa OAuth con la **contraseña del propietario**, no la contraseña de Apple. Configura aprobación para escrituras y refresca las herramientas. En ChatGPT el nombre de la opción puede variar; utiliza la acción de actualizar herramientas del conector. El número depende de `read_only` y las funciones activas; el catálogo completo de las cuatro áreas más reloj contiene 59 herramientas.

Primero pide diagnóstico y lectura de listas. Las pruebas que creen, envíen o borren datos requieren una instrucción explícita. Un diagnóstico correcto no prueba sincronización ni avisos del iPhone.

## Límites de disponibilidad

El Mac y la sesión deben estar disponibles; el Keychain puede requerir desbloqueo después de reiniciar. `start` no modifica reposo, inicio automático de sesión ni ajustes de seguridad del sistema. Usa `stop` antes de cambiar la URL/puerto y vuelve a `start`. Cambiar URL puede requerir reconectar OAuth en el cliente.
