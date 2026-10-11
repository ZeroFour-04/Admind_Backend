# reservas

Alcance: Núcleo (§3.1).

El flujo de reserva de zonas comunes. El orden de llegada decide quién puede pedir; una persona decide quién obtiene.

## Qué va aquí

- Modelo de **solicitud**: el estado vive aquí, no en la franja. El calendario no se guarda en la base
- Estados bloqueantes `EN_SOLICITUD`, `APARTADA`, `RESERVADA`; no bloqueantes `RECHAZADA`, `CANCELADA`, `EXPIRADA`
- Bloqueo de **3 minutos**, constante del sistema, con un solo bloqueo activo por residente
- **Dos oportunidades** por par `(residente, franja)`; solo cuenta el vencimiento (R9)
- Aprobación con **condiciones del alquiler** obligatorias, congeladas al aprobar y versionadas si cambian
- Rechazo con categoría obligatoria: `NO_DISPONIBLE`, `CONDICIONES_NO_CUMPLIDAS`, `DOCUMENTACION_INCOMPLETA`, `INCUMPLE_REGLAMENTO`, `OTRO`
- Bandeja administrativa por zona común para revisar solicitudes enviadas, aceptar o rechazar con motivo auditado
- Pago **declarado**, no validado (HU-16, construido el 2026-10-10): `Solicitud.pago_declarado_por` y `pago_declarado_en` (van los dos o ninguno, por un `CHECK`) y `ComprobanteDePago`, con el archivo dentro de la base. Vive en `pago.py`: declarar (solo `reserva.declarar_pago`, es decir Administración), retirar la declaración con motivo, subir el residente su comprobante (máximo 3, y no cambia el estado del pago) y decidir quién descarga. Aprobar una reserva no depende del pago
- **Campana:** suscripción a una franja concreta, que se consume al notificar
- Fechas de **alta demanda**, con FIFO puro sobre el momento de tomar el bloqueo

## Con qué se conecta

- `apps/comun/bloqueo/`: el bloqueo y la transacción no se implementan aquí
- `apps/comun/archivos/`: la validación del comprobante por su firma (PDF, JPG o PNG, hasta 5 MB, con SHA-256); la comparte con el pago de administración
- `apps/reglas/`: valida la solicitud al enviarla
- `apps/areas/`: la franja es sobre un área
- `apps/unidades/`: solo solicita quien tiene vínculo vigente con `reside = true`
- `apps/notificaciones/`: campana, aprobación y rechazo
- `apps/triage/`: las solicitudes aparecen como **Evento** en la bandeja, solo por antigüedad
- `apps/auditoria/`: cada cambio de estado con hora y actor
- `tests/concurrencia/`: las pruebas obligatorias de §5.1
- Frontend: `Admind_Front-End/apps/reservas/`

## Referencias

Maestro §5.1 · HU-11 · R7, R8, R9 · Decisiones §9: 11, 12, 13, 17, 18

## Pendiente

- "Un solo bloqueo activo en todo el sistema" contra "toda clave única incluye `conjunto_id`" (§12.7 c)
