# modelos_base

Modelos abstractos de Django con lo que repiten casi todas las entidades. Si un campo obligatorio vive aquí, nadie puede olvidarlo en una tabla nueva.

## Qué va aquí

- Llave primaria **UUID** (§5.2)
- `conjunto` obligatorio y la clave única `(id, conjunto)` que necesitan las FK compuestas (§5.4, §7.1)
- **Anulación:** `anulado`, `motivo_anulacion` (no admite vacío), `anulado_por`, `fecha_anulacion`. La fila queda consultable y tachada (§5.3)
- **Baja lógica:** `activo` para personas y conjuntos; `vigencia_desde` y `vigencia_hasta` para vínculos y asignaciones (§5.11)

## Lo que no va

Ningún método de borrado. Las entidades de §5.11 no exponen esa operación.

## Con qué se conecta

- Todas las apps con datos heredan de aquí
- Las tablas globales de la lista cerrada (§5.4) usan el UUID pero **no** el campo `conjunto`
- `apps/comun/aislamiento/`: su manager se engancha en estos modelos

## Referencias

Maestro §5.2, §5.3, §5.4, §5.11 · Decisiones §9: 16, 21, 24
