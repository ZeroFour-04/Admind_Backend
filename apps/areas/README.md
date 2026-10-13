# areas

Alcance: Núcleo (§3.1).

Catálogo de zonas comunes de cada conjunto: salón comunal, piscina, gimnasio y las que el conjunto agregue.

## Qué va aquí

- Modelo de área por conjunto: se identifica por nombre dentro del conjunto, sin tipo ni clasificación
- **Modo de uso** (`modo_uso`): `reserva` (el valor de las áreas que ya existían) o `ingreso`. Se elige al crear y **se puede cambiar** con `PATCH`, que entonces exige el dato del modo nuevo y vacía el del anterior. `CHECK area_modo_coherente`
- **Cambiar el modo** (`servicios.cambiar_modo`) no toca lo que ya existe: las reservas apartadas o reservadas siguen válidas y quien está adentro sigue adentro. Retira las reglas del área que no aplican al modo nuevo y la respuesta trae `cambio_de_modo` (`reservas_por_cumplir`, `personas_adentro`, `reglas_retiradas`); llega vacío si el modo no cambió. En la auditoría queda como `area.cambiar_modo`
- Con reserva: `duracion_franja_minutos` obligatoria (al menos 120 minutos) y sin permanencia. Con ingreso: `permanencia_maxima_minutos` obligatoria (de 15 a 1 440) y sin duración
- Un área con ingreso no se reserva: `franjas_del_dia` devuelve una lista vacía
- Cada área lleva un **aforo máximo** obligatorio, de 1 a 10 000: toda solicitud se compara con él
- Administración puede guardar una plantilla de **condiciones del alquiler** por área; se devuelve con los datos del área y precarga la aprobación de una reserva

## Con qué se conecta

- `apps/ingresos/`: el registro de entradas y salidas de las áreas con ingreso
- `apps/reservas/`: una franja es `(area, fecha, hora_inicio, hora_fin)`, con FK compuesta `(area_id, conjunto_id)`
- `apps/reglas/`: las reglas beta son de un área, y el evaluador lee de aquí el aforo. Al cambiar el modo se le pide retirar las que ya no aplican (`import` tardío: `reglas`, `reservas` e `ingresos` ya importan esta app)
- `apps/conjuntos/`: el asistente exige el catálogo antes de activar el conjunto
- Frontend: `Admind_Front-End/apps/areas/`

## Referencias

Maestro §3.1, §5.1, §5.4, §5.10
