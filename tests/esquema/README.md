# esquema

Pruebas que recorren el esquema de la base en lugar de llamar a un endpoint.

## Qué va aquí

- **Tablas globales:** la prueba falla si una tabla fuera de la lista cerrada no tiene `conjunto_id` (R12)
- **Auditoría de solo inserción:** un `UPDATE` o `DELETE` del usuario de aplicación sobre auditoría tiene que fallar (§7.2, punto 3)
- Ninguna FK con `ON DELETE CASCADE` (§5.11)

## Con qué se conecta

- `apps/comun/modelos_base/`, `apps/auditoria/` y `bd/`

## Referencias

Maestro §5.4, §5.11, §7.2 · R12

## Pendiente

- Escribir la lista cerrada de tablas globales (R12, §11.5)
