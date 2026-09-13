# importacion_respaldo

Alcance: Comprometido (§3.2).

Carga masiva desde CSV o Excel y generación de respaldos del conjunto.

## Qué va aquí

- Importación masiva (`importacion.ejecutar`)
- Generación de respaldo (`respaldo.generar`, permiso sensible)

## Lo que no existe

Borrado masivo. Ninguna operación borra o desactiva por filtro; siempre por identificador (§5.11).

## Con qué se conecta

- `apps/personas/` y `apps/unidades/`: lo que se importe pasa por las mismas validaciones que el alta manual, normalización del documento incluida
- `apps/auditoria/`
- `bd/`: el procedimiento de respaldo y restauración de la base
- Frontend: `Admind_Front-End/apps/importacion_respaldo/`

## Referencias

Maestro §3.2, §5.3, §5.11

## Pendiente

- ¿Documento obligatorio desde el alta? Exigirlo bloquea la importación masiva (§11.6)
