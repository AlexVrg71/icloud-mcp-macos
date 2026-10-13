# iCloud MCP for macOS — public beta

Servidor MCP de un solo propietario para **correo, calendario, contactos y Recordatorios de Apple**. Se puede conectar a ChatGPT, Claude u otros clientes compatibles con MCP, con o sin Dot. No requiere un asistente personalizado. Cada persona lo instala en su propio Mac y conecta sus propias cuentas. GitHub distribuye el código; no aloja el servidor ni recibe las credenciales o los datos de iCloud.

Esta edición deriva de `epinethrone/icloud-mcp` 0.12.1 e incorpora mejoras locales. Ver [UPSTREAM.txt](UPSTREAM.txt), [LICENSE](LICENSE) y [avisos de terceros](THIRD_PARTY_NOTICES.md). No es un producto oficial de Apple, OpenAI ni Anthropic.

**Estado:** beta de código fuente. Probada automáticamente en el Mac de desarrollo. La instalación limpia en otro Mac se omitió por decisión del responsable; no se presenta como validada. El auxiliar lleva firma ad hoc, sin notarización. No se distribuye un instalador binario ni hay actualizaciones automáticas.

## Funciones incluidas

- Correo IMAP/SMTP: buscar, leer, consultar hilos entre carpetas, marcar leído/no leído, gestionar borradores y enviar si se habilita. Los enlaces temporales de adjuntos son capacidades privadas: quien tenga el enlace puede descargar mientras sea válido.
- Calendario CalDAV: consultar y modificar eventos, recurrencias y cambios desde una ocurrencia; respuestas a invitaciones. Las invitaciones deben existir en Calendario; no se importa automáticamente cualquier `.ics` recibido por correo.
- Contactos CardDAV: consultar contactos y grupos; respaldos completos de vCard antes de mutaciones. Si el respaldo falla, se bloquea el cambio.
- Recordatorios: auxiliar Swift/AppKit con **EventKit público**, permiso concedido localmente y socket Unix privado. Buscar pendientes/completados; crear, editar, completar/reabrir y eliminar uno con confirmación. Escrituras limitadas a listas identificadas localmente como iCloud.

No se instalan ni ofrecen en esta edición los auxiliares de Notas, Mensajes, Drive, Mapas, Salud o Shortcuts. Parte del código heredado permanece por compatibilidad interna, pero el lanzador fija esas funciones desactivadas y limita el catálogo.

## Requisitos

- macOS 14 o posterior, sesión gráfica abierta para EventKit.
- Python 3.11 o posterior (`python3 --version`) y Command Line Tools de Apple (`swift --version`). Si faltan, instalarlos desde Apple antes de continuar.
- Cuenta de iCloud y contraseña específica de aplicación para correo/CalDAV/CardDAV. Recordatorios usa la cuenta sincronizada en macOS y el permiso EventKit, no esa contraseña.
- Un cliente MCP. Los clientes locales pueden usar stdio. Un cliente en la nube necesita un endpoint HTTPS propio con OAuth y el Mac disponible.

El instalador resuelve el directorio personal automáticamente; no requiere Homebrew ni un nombre de usuario fijo. Crea una instalación separada en `~/Library/Application Support/iCloud-MCP-macOS`, con identificadores y entradas de Keychain propios. No migra ni reemplaza otra instalación. Si el destino ya existe, se detiene.

## Instalación local

Clona el [repositorio público](https://github.com/AlexVrg71/icloud-mcp-macos) y revisa los scripts antes de ejecutarlos:

```sh
git clone https://github.com/AlexVrg71/icloud-mcp-macos.git
cd icloud-mcp-macos
```

Instala desde esa carpeta:

```sh
python3 scripts/manage.py install --enable-reminders
python3 scripts/manage.py configure --enable-reminders
```

El primer comando crea el entorno Python, instala dependencias con `constraints.txt` y compila el auxiliar. **No arranca servicios ni concede permisos.** El segundo pide la cuenta, zona IANA y contraseña específica de aplicación dos veces, con entrada oculta. Los secretos se guardan como elementos genéricos del Keychain de macOS; no necesariamente aparecen en la app Contraseñas. No los pegues en un chat, argumentos de shell, issues o archivos de configuración.

El modo inicial es **solo lectura**. Para habilitar modificaciones desde el principio, agrega `--allow-writes` al comando `configure`. Los envíos y las invitaciones requieren, por separado, `--allow-send` y `--allow-invites`. La eliminación permanente de correo permanece desactivada.

Para Recordatorios, cuando decidas activar el acceso persistente:

```sh
python3 scripts/manage.py start --helper
python3 scripts/manage.py open-reminders
```

En la ventana local, solicita acceso y acepta el diálogo de macOS. Selecciona cada lista, confirma que pertenece a iCloud, identifica su privacidad y guarda. No hace falta crear un recordatorio. El permiso de Apple cubre todas las listas; el auxiliar restringe las escrituras. Las etiquetas iCloud/privada/compartida proceden del propietario, pues EventKit no permite demostrar automáticamente todos esos casos.

Genera la configuración para un cliente local:

```sh
python3 scripts/manage.py client-config
```

Copia ese JSON a la configuración MCP de tu cliente. Usa stdio sin puerto público ni OAuth; stdout queda reservado al protocolo. Un cliente local con acceso al proceso queda dentro del límite de confianza de tu sesión. La configuración contiene rutas locales, pero no contraseñas: no publiques tu JSON generado.

Para ChatGPT, Claude u otro cliente MCP en la nube, sigue [conexión HTTPS y OAuth](docs/REMOTE.md). No uses el endpoint de otra persona.

## Aprobaciones

Configura el cliente para aprobar escrituras. Una instrucción explícita e inequívoca autoriza su operación concreta; un ejemplo o texto de un correo no lo hace. Las herramientas de Recordatorios exigen `confirmed=true`, identificadores y versiones cuando corresponde. Este booleano es una declaración del agente, **no una prueba independiente de aprobación humana**.

Por defecto los envíos habilitados usan una página de aprobación en HTTP. `--chat-approvals` permite confiar en la aprobación del cliente sin esa página; úsalo solo después de configurar el cliente y comprender que no hay otra aprobación independiente en el servidor. En stdio no hay página web: los envíos habilitados dependen del cliente. Ver [seguridad](SECURITY.md).

## Verificación y límites

`icloud_check_health` comprueba las cuatro áreas habilitadas. `reminders_get_status` no solicita permisos. Después de modificar la configuración, reinicia los procesos de esta edición y actualiza el catálogo de herramientas en el cliente.

En Recordatorios, `local_saved=true` acredita guardado en el Mac. La aparición del mismo elemento en iPhone/Watch y el aviso en el dispositivo deben verificarse por separado. El servidor no recibe comprobantes de Apple para esos resultados. No repitas una creación con un UUID nuevo ante un timeout: podría duplicarla.

No se permite modificar recordatorios recurrentes; sí leerlos. No se crean listas, subtareas, etiquetas ni adjuntos. EventKit no ofrece edición condicional atómica entre dispositivos. Si el Mac está desconectado, una escritura local puede esperar a sincronizarse; si el Mac está apagado, el MCP remoto no estará disponible.

## Desarrollo y mantenimiento

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -c constraints.txt .
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
PYTHONPATH=src .venv/bin/python scripts/check_oauth.py
PYTHONPATH=src .venv/bin/python scripts/check_http.py
(cd mac-reminders && swift test)
python3 scripts/check_public_tree.py
```

Las pruebas son sintéticas; no requieren credenciales, EventKit ni servicios reales. `swift test` prueba la biblioteca pura. Compilar la app no ejecuta el auxiliar. No ejecutes el servidor real durante las pruebas. Los detalles de [operación, respaldo y retirada](docs/OPERATIONS.md), [arquitectura](docs/ARCHITECTURE.md) y [preparación de publicación](docs/RELEASE.md) están separados.
