# areas

Alcance: Núcleo (§3.1).

Catálogo de zonas comunes de cada conjunto: salón comunal, piscina, gimnasio y las que el conjunto agregue.

## Qué va aquí

- Modelo de área por conjunto: se identifica por nombre dentro del conjunto, sin tipo ni clasificación
- **Modo de uso** (`modo_uso`): `reserva` (el valor de las áreas que ya existían) o `ingreso`. Se elige al crear y **no cambia**: `PATCH` con `modo_uso` responde 400. `CHECK area_modo_coherente`
- Con reserva: `duracion_franja_minutos` obligatoria (al menos 120 minutos) y sin permanencia. Con ingreso: `permanencia_maxima_minutos` obligatoria (de 15 a 1 440) y sin duración
- Un área con ingreso no se reserva: `franjas_del_dia` devuelve una lista vacía
- Cada área lleva un **aforo máximo** obligatorio, de 1 a 10 000: toda solicitud se compara con él
- Plantilla de **condiciones del alquiler** por área, que precarga la aprobación de una reserva

## Con qué se conecta

- `apps/ingresos/`: el registro de entradas y salidas de las áreas con ingreso
- `apps/reservas/`: una franja es `(area, fecha, hora_inicio, hora_fin)`, con FK compuesta `(area_id, conjunto_id)`
- `apps/reglas/`: las reglas beta son de un área, y el evaluador lee de aquí el aforo
- `apps/conjuntos/`: el asistente exige el catálogo antes de activar el conjunto
- Frontend: `Admind_Front-End/apps/areas/`

## Referencias

Maestro §3.1, §5.1, §5.4, §5.10
