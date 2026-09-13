# triage

Alcance: Comprometido (§3.2).

La bandeja de Secretaría. La Secretaría **no decide, clasifica**: filtra la forma y le deja el fondo al administrador.

## Qué va aquí

- La **bandeja**, que es una vista y no una entidad: pestañas de Citas, Casos y Eventos, más la vista combinada
- **Prioridad** `BAJA · NORMAL · ALTA · URGENTE`. `NORMAL` la pone el sistema; `URGENTE` exige justificación. Sobre Eventos la operación no existe y responde 400
- Orden fijo `prioridad DESC, fecha_creacion ASC`, no configurable, y la vista por antigüedad pura
- **Rechazo formal:** terminal, con causal de lista cerrada, sin `OTRO`
- Funciona con cero secretarías: en un conjunto pequeño el administrador es la secretaría

## Lo que no va

Aprobar, responder de fondo, reasignar o exportar.

## Con qué se conecta

- `apps/citas/`, `apps/casos/`, `apps/reservas/`: las tres solicitudes que llegan a la bandeja
- `apps/auditoria/`: todo cambio de prioridad, con valor anterior y nuevo
- `apps/notificaciones/`: el rechazo formal de un Evento libera la franja y avisa a los suscritos
- Frontend: `Admind_Front-End/apps/triage/`

## Referencias

Maestro §5.7 · HU-22 · R13 · Decisiones §9: 19, 27, 28, 30

## Pendiente

- Las tres listas de causales formales (R13, §11.4)
- HU-22 depende de HU-29 y HU-31 (§12.5)
