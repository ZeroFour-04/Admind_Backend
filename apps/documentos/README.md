# documentos

Alcance: Comprometido (§3.2). El reglamento cargado sí es requisito del Núcleo para activar un conjunto.

El repositorio de documentos del conjunto: reglamento, actas, comprobantes.

## Qué va aquí

- Metadatos de cada documento y sus reglas de acceso
- Archivos en almacenamiento **no público**, con ruta `conjunto/{uuid}/documentos/{uuid}.pdf`
- Descarga solo por endpoint validado (`documento.descargar`, permiso sensible)
- Actas de asamblea solo para propietarios autenticados: basta el adjunto más metadatos (§3.4)

## Qué hay hoy

El reglamento (2026-10-06) y, desde el 2026-10-25 (HU-33, rama `feat/documentos-por-tipo`, sin commit), el manual de convivencia. El reglamento es el único requisito del asistente (HU-03); el manual es opcional.

- `Documento` (`ModeloDeConjunto`, antes `Reglamento`; `documentos/0002` lo renombró sin perder filas) con `tipo` (`reglamento` o `manual`): el PDF en la base (`BinaryField`), con `nombre`, `peso`, `huella` (SHA-256), `subido_por` y `subido_en`. No en almacenamiento de archivos: se guarda como la foto del conjunto
- `servicios.guardar()` revisa que no esté vacío, que pese hasta 10 MB y que empiece por `%PDF-`. **Subir otro no borra el anterior:** el vigente de cada tipo es el más reciente y los demás quedan como versiones archivadas
- `servicios.vigente(tipo)`, `vigentes()`, `versiones(tipo)` y `version(tipo, id)` dejan el contenido fuera con `defer`, salvo que se pida; `registrar_descarga` audita cada descarga

`<tipo>` es `reglamento` o `manual`; cualquier otro es 404 antes de llegar a la vista (convertidor de ruta).

| Método | Ruta | Permiso | Respuestas |
|---|---|---|---|
| `GET` | `/documentos/` | `documento.ver` o `documento.subir` | 200 con una entrada por tipo: `tipo`, `tipo_nombre`, `cargado` y, si está cargado, `id`, `nombre`, `peso`, `subido_en`, `subido_por` |
| `GET` | `/documentos/<tipo>/` | `documento.ver` o `documento.subir` | 200 con lo mismo, de un tipo |
| `PUT` | `/documentos/<tipo>/` | `documento.subir` | 200 con los datos del nuevo · 400 con el error en `archivo` (multipart, campo `archivo`) |
| `GET` | `/documentos/<tipo>/archivo/` | `documento.ver`, `documento.subir` o `documento.descargar` | 200 con el PDF vigente, **auditado** · 404 si no hay |
| `GET` | `/documentos/<tipo>/versiones/` | `documento.descargar` (sensible) | 200 con todas las versiones, la vigente primero (`vigente`) |
| `GET` | `/documentos/<tipo>/versiones/<id>/archivo/` | `documento.descargar` (sensible) | 200 con el PDF de esa versión, **auditado** · 404 |

Falta de HU-33: las actas de asamblea (solo para propietarios), que no entran por decisión de Alejo (D2 b).

## Con qué se conecta

- `apps/conjuntos/`: el asistente exige el reglamento
- `apps/reservas/` y `apps/pagos/`: los comprobantes
- `apps/unidades/`: quién es propietario, para las actas
- Frontend: `Admind_Front-End/apps/documentos/`

## Referencias

Maestro §3.4, §4.2, §5.4
