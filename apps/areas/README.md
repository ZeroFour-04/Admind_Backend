# areas

Alcance: Núcleo (§3.1).

Catálogo de zonas comunes de cada conjunto: salón comunal, piscina, gimnasio y las que el conjunto agregue.

## Qué va aquí

- Modelo de área por conjunto: se identifica por nombre dentro del conjunto, sin tipo ni clasificación
- Cada franja reservable dura al menos 120 minutos (2 horas)
- Plantilla de **condiciones del alquiler** por área, que precarga la aprobación de una reserva

## Con qué se conecta

- `apps/reservas/`: una franja es `(area, fecha, hora_inicio, hora_fin)`, con FK compuesta `(area_id, conjunto_id)`
- `apps/reglas/`: las reglas beta se configuran por área
- `apps/conjuntos/`: el asistente exige el catálogo antes de activar el conjunto
- Frontend: `Admind_Front-End/apps/areas/`

## Referencias

Maestro §3.1, §5.1, §5.4, §5.10
