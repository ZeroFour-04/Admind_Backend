# bloqueo

El mecanismo compartido de "recurso limitado + concurrencia" (R1). Reservas, citas y parqueadero de visitantes tienen reglas de negocio distintas, pero el bloqueo y la transacción son uno solo.

## Qué va aquí

- Tomar y soltar un bloqueo exclusivo dentro de una transacción (`transaction.atomic`, `select_for_update`)
- Expiración evaluada **al siguiente acceso**: idempotente, sin ningún proceso corriendo en segundo plano

## Lo que no va

La red de seguridad final. Esa es el índice único parcial en PostgreSQL, que se declara en la migración de cada app que use el bloqueo.

## Con qué se conecta

- `apps/reservas/`: bloqueo de 3 minutos sobre una franja
- `apps/citas/`: agendamiento con el administrador
- `apps/visitantes/`: ocupación temporal del parqueadero de visitantes
- `tests/concurrencia/`: N peticiones simultáneas producen exactamente un bloqueo

## Referencias

Maestro §5.1, §5.9, §7.2 (punto 2) · R1, R7 · Decisión §9: 2
