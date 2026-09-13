# concurrencia

Las pruebas obligatorias del flujo de reserva (§5.1). Es de lo que más se sustenta.

## Qué va aquí

- N solicitudes simultáneas sobre la misma franja producen **exactamente un** bloqueo
- Un bloqueo vencido no bloquea
- Un bloqueo liberado a mano no expira dos veces
- La apertura de la ventana de anticipación con N residentes en el mismo segundo no duplica reservas

## Con qué se conecta

- `apps/comun/bloqueo/` y `apps/reservas/`
- PostgreSQL real: el índice único parcial no existe en SQLite (§7.1)

## Referencias

Maestro §5.1, §7.2 (punto 2) · HU-11 · R7
