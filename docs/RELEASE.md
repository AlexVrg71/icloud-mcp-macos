# Publicación y validación — 0.1.0b1

Repositorio público: [https://github.com/AlexVrg71/icloud-mcp-macos](https://github.com/AlexVrg71/icloud-mcp-macos). El historial empieza con un snapshot nuevo de código fuente y excluye el historial privado del despliegue. No se ha publicado el paquete en PyPI.

## Criterios para mantener la publicación

1. Revisar el snapshot y `python3 scripts/check_public_tree.py`. El control detecta patrones frecuentes, archivos privados y rutas personales; no garantiza detectar todo secreto posible.
2. Mantener `LICENSE`, `UPSTREAM.txt` y avisos. Usar metadatos públicos o una dirección noreply de GitHub para los commits. No importar el historial de despliegue privado.
3. Mantener Private vulnerability reporting habilitado y el canal de `SECURITY.md` vigente. La metadata del paquete enlaza a este repositorio.
4. Revisar el workflow de GitHub Actions: solo pruebas sintéticas, `contents: read`, sin secretos ni publicación automática. La ejecución remota se consulta en [GitHub Actions](https://github.com/AlexVrg71/icloud-mcp-macos/actions/workflows/checks.yml); los resultados locales de abajo no sustituyen ese estado.
5. Publicar solo fuentes y documentación revisadas. Excluir `.venv`, `.build`, `build`, `data`, logs, respaldos, config, secretos, paquetes compilados y cualquier evidencia de dispositivos. La firma ad hoc de desarrollo no es una distribución notarizada.

**Omisión aceptada:** instalación limpia en otro Mac. No es requisito pendiente para este paquete por decisión del responsable; se mantiene como límite de validación. No se pidió acceso a cuentas ni permisos TCC durante la preparación pública.

## Validación reproducible

Consultar [README](../README.md) para comandos. La suite usa objetos ficticios, sockets temporales y transporte HTTP en memoria. Nunca usa el servidor en ejecución, el Keychain real ni recordatorios del propietario. La utilidad Keychain se compila y sus invocaciones se prueban con mocks; la configuración interactiva con credenciales no se ejecuta como prueba.

La prueba de regresión verifica las 50 herramientas anteriores y las ocho de Recordatorios más el reloj al habilitarlos. El catálogo en solo lectura es menor. Las pruebas de OAuth abarcan raíz y prefijo, PKCE, contraseña rechazada, denegación y código de un uso. La biblioteca Swift verifica fechas/zonas, permisos de listas, UUID/versión y resultados inciertos.

Actualizar este documento y `CHANGELOG.md` en cada versión. No elevar la etiqueta beta ni afirmar compatibilidad en otros equipos sin evidencia.

## Resultado local de la preparación

- 67 pruebas Python y 28 pruebas Swift: PASS. Incluyen 21 pruebas nuevas de portabilidad, aislamiento y políticas del instalador.
- OAuth raíz/prefijo, catálogo HTTP y descargas sintéticas: PASS.
- Bundle EventKit y utilidad nativa de Keychain: compilación PASS. Firma local del bundle verificada; no se abrió la app.
- Dependencias instaladas en un entorno virtual separado; no se ejecutó la instalación funcional ni se modificó el despliegue existente.
- Revisión de fuentes y control de higiene: sin hallazgos pendientes. Esto no es una certificación de ausencia universal de secretos.

`python3 scripts/package_source.py` genera un ZIP de fuentes en `dist/` con `SHA256SUMS` interno. No añade `.git`, entornos, ejecutables, registros ni datos de ejecución. El archivo resultante es el candidato a compartir; no uses un ZIP de todo el directorio de trabajo.
