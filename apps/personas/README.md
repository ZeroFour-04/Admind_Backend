# personas

Alcance: Núcleo (§3.1).

La identidad. Una persona es una sola fila en toda la plataforma, aunque tenga roles en varios conjuntos.

## Qué va aquí

- Modelo `Persona`: **tabla global**, sin `conjunto_id`. PK UUID; se identifica por `UNIQUE (tipo_documento, numero_documento)`
- `tipo_documento` de lista cerrada: `CC`, `TI`, `CE`, `PAS`, `PPT`. Códigos sin puntos; el nombre completo es solo presentación
- Normalización del número **al guardar**: sin puntos, sin espacios, sin ceros a la izquierda
- Búsqueda **por documento exacto** y vinculación al conjunto activo
- Baja lógica (`activo`). Desactivar una persona **no** la desvincula de sus conjuntos

## Lo que no va

Búsqueda libre por nombre: sobre una tabla global sería un directorio de toda la plataforma (§3.4).

## Con qué se conecta

- `apps/permisos/`: `Asignacion` referencia a la persona
- `apps/unidades/`: `VinculoUnidad` referencia a la persona
- `apps/cuentas/`: cada usuario corresponde a una persona
- `tests/esquema/`: `Persona` está en la lista cerrada de tablas globales
- Frontend: `Admind_Front-End/apps/personas/`

## Referencias

Maestro §5.2, §5.11 · R12 · Decisiones §9: 23, 24

## Pendiente

- Tope de búsquedas por documento por administrador y ventana de tiempo (R12, §11.5)
- ¿Documento obligatorio desde el alta? (§11.6)
