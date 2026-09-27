# bloqueo

El mecanismo compartido de "recurso limitado + concurrencia" (R1). Reservas, citas y parqueadero de visitantes tienen reglas de negocio distintas, pero el bloqueo y la transacción son uno solo.

## Qué hay aquí

- `bloqueo.py`:
  - `tomar(crear)`: corre `crear()` dentro de `transaction.atomic()` y convierte el `IntegrityError` del índice único parcial en `RecursoOcupado`, con el nombre del índice que falló en `restriccion`. No consulta antes si el recurso está libre: decide la base
  - `expirar_vencidos(queryset, *, campo_vence, estado_activo, estado_expirado, ahora)`: un solo `UPDATE ... WHERE estado = activo AND vence <= ahora`. Se llama **al siguiente acceso**: es idempotente y no depende de ningún proceso en segundo plano
- No importa ninguna app de negocio

## Lo que no va

La red de seguridad final. Esa es el índice único parcial en PostgreSQL, que se declara en la migración de cada app que use el bloqueo (en reservas, `solicitud_franja_bloqueante_unica` y `solicitud_un_bloqueo_por_persona`).

## Con qué se conecta

- `apps/reservas/`: bloqueo de 3 minutos sobre una franja (HU-11)
- `apps/citas/`: agendamiento con el administrador
- `apps/visitantes/`: ocupación temporal del parqueadero de visitantes
- `tests/concurrencia/`: N peticiones simultáneas producen exactamente un bloqueo

## Referencias

Maestro §5.1, §5.9, §7.2 (punto 2) · R1, R7 · Decisión §9: 2
