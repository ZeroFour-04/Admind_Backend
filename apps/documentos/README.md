# documentos

Alcance: Comprometido (§3.2). El reglamento cargado sí es requisito del Núcleo para activar un conjunto.

El repositorio de documentos del conjunto: reglamento, actas, comprobantes.

## Qué va aquí

- Metadatos de cada documento y sus reglas de acceso
- Archivos en almacenamiento **no público**, con ruta `conjunto/{uuid}/documentos/{uuid}.pdf`
- Descarga solo por endpoint validado (`documento.descargar`, permiso sensible)
- Actas de asamblea solo para propietarios autenticados: basta el adjunto más metadatos (§3.4)

## Qué hay hoy

Solo el reglamento del conjunto, que es lo que el asistente exige (HU-03). Construido el 2026-10-06.

- `Reglamento` (`ModeloDeConjunto`): el PDF en la base (`BinaryField`), con `nombre`, `peso`, `huella` (SHA-256), `subido_por` y `subido_en`. No en almacenamiento de archivos: se guarda como la foto del conjunto
- `servicios.guardar()` revisa que no esté vacío, que pese hasta 10 MB y que empiece por `%PDF-`. **Subir otro no borra el anterior:** el vigente es el más reciente
- `servicios.vigente()` deja el contenido fuera con `defer`, salvo que se pida

| Método | Ruta | Permiso | Respuestas |
|---|---|---|---|
| `GET` | `/documentos/reglamento/` | `documento.ver` o `documento.subir` | 200 con `{"cargado": false}` o con `nombre`, `peso`, `subido_en` y `subido_por` |
| `PUT` | `/documentos/reglamento/` | `documento.subir` | 200 con los datos del nuevo · 400 con el error en `archivo` (multipart, campo `archivo`) |
| `GET` | `/documentos/reglamento/archivo/` | `documento.descargar` o `documento.subir` | 200 con el PDF · 404 si no hay |

Falta el resto de HU-33: otros documentos, las actas y que el residente descargue el reglamento.

## Con qué se conecta

- `apps/conjuntos/`: el asistente exige el reglamento
- `apps/reservas/` y `apps/pagos/`: los comprobantes
- `apps/unidades/`: quién es propietario, para las actas
- Frontend: `Admind_Front-End/apps/documentos/`

## Referencias

Maestro §3.4, §4.2, §5.4
