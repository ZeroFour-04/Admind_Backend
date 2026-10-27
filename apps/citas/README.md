# citas

Alcance: Comprometido (§3.2).

Citas de un residente con el administrador. Módulo a la medida: no reutiliza el motor de reservas, pero sí el bloqueo compartido.

## Qué va aquí

- `HorarioDeAtencion`: una configuración semanal por conjunto. Cada día puede tener horas de atención y un intervalo opcional de descanso
- `GET /citas/horario/`: Administración y residentes con `cita.agendar_propia` pueden consultar el horario; `PUT` sigue limitado a `cita.gestionar_horario` y registra los cambios en auditoría
- `Cita`: franja de dos horas, con estados `AGENDADA` y `ATENDIDA`; solo se permite una futura por residente y conjunto
- `GET /citas/agenda/`: horario, cita propia y disponibilidad opcional por fecha; `POST /citas/agenda/`: agenda una franja futura
- `GET /citas/bandeja/`: lista de citas del conjunto para `cita.ver_todas`
- La disponibilidad excluye el descanso. La creación usa el bloqueo compartido R1, serializa por conjunto y cuenta con índices únicos parciales para la franja y la cita activa por persona
- Cambio de horario: detecta las citas que quedan fuera, exige explicación, las pasa a `CANCELADA_POR_ADMIN` y ofrece **tres alternativas** que no se solapan entre afectados
- El contrato de triage de tres campos (§5.7)

## Con qué se conecta

- `apps/comun/bloqueo/`: exclusión y expiración de citas (R1)
- `apps/triage/`: Administración consulta la lista de citas; prioridad y gestión formal siguen pendientes
- `apps/notificaciones/`: aviso con la explicación y las alternativas
- Frontend: `Admind_Front-End/apps/citas/`

## Referencias

Maestro §5.7, §5.9 · HU-31 · R1

## Pendiente

- Cambio de horario con citas existentes, explicación, cancelaciones, alternativas y notificaciones aún no están implementados
- Gestión administrativa de estados y aceptación/rechazo formal de citas aún no está implementada
- Lista cerrada de causales formales de rechazo (R13, §11.4)
