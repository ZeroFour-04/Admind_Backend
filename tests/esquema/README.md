# esquema

Pruebas que recorren el esquema de la base en lugar de llamar a un endpoint.

## Qué va aquí

- **Tablas globales:** la prueba falla si una tabla fuera de la lista cerrada no tiene `conjunto_id` (R12)
- **Auditoría de solo inserción:** el manager y el modelo rechazan `UPDATE` y `DELETE`; el trigger de base queda pendiente
- **Funciones de reportes y aforo:** ocupación, estado de pagos, resumen de casos y aforo actual reciben el conjunto explícitamente; la prueba cubre resultados y errores
- **Procedimiento de expiración:** se invoca con `CALL` y solo cambia bloqueos vencidos del conjunto indicado
- **Triggers C5:** cinco triggers bloquean el borrado físico en reservas, pagos, casos e infracciones, y la edición de infracciones ya anuladas
- Ninguna FK con `ON DELETE CASCADE` (§5.11)

## Con qué se conecta

- `apps/comun/modelos_base/`, `apps/auditoria/` y `bd/`

## Referencias

Maestro §5.4, §5.11, §7.2 · R12

## Pendiente

- Escribir la lista cerrada de tablas globales (R12, §11.5)
- Por el límite de cinco triggers de C5, quedan pendientes la inmutabilidad SQL de auditoría y las normalizaciones SQL de correo y documento
