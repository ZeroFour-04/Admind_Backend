# citas

Alcance: Comprometido (§3.2).

Citas de un residente con el administrador. Módulo a la medida: no reutiliza el motor de reservas, pero sí el bloqueo compartido.

## Qué va aquí

- Horario de atención del administrador y agendamiento de citas
- Cambio de horario: detecta las citas que quedan fuera, exige explicación, las pasa a `CANCELADA_POR_ADMIN` y ofrece **tres alternativas** que no se solapan entre afectados
- El contrato de triage de tres campos (§5.7)

## Con qué se conecta

- `apps/comun/bloqueo/`: agendar compite por un recurso limitado (R1)
- `apps/triage/`: aparece en la bandeja, por prioridad y luego antigüedad
- `apps/notificaciones/`: aviso con la explicación y las alternativas
- Frontend: `Admind_Front-End/apps/citas/`

## Referencias

Maestro §5.7, §5.9 · HU-31 · R1

## Pendiente

- Lista cerrada de causales formales de rechazo (R13, §11.4)
