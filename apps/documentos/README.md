# documentos

Alcance: Comprometido (§3.2). El reglamento cargado sí es requisito del Núcleo para activar un conjunto.

El repositorio de documentos del conjunto: reglamento, actas, comprobantes.

## Qué va aquí

- Metadatos de cada documento y sus reglas de acceso
- Archivos en almacenamiento **no público**, con ruta `conjunto/{uuid}/documentos/{uuid}.pdf`
- Descarga solo por endpoint validado (`documento.descargar`, permiso sensible)
- Actas de asamblea solo para propietarios autenticados: basta el adjunto más metadatos (§3.4)

## Con qué se conecta

- `apps/conjuntos/`: el asistente exige el reglamento
- `apps/reservas/` y `apps/pagos/`: los comprobantes
- `apps/unidades/`: quién es propietario, para las actas
- Frontend: `Admind_Front-End/apps/documentos/`

## Referencias

Maestro §3.4, §4.2, §5.4
