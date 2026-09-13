# tests

Pruebas que no pertenecen a un solo módulo. Las pruebas unitarias de cada módulo viven dentro de su app.

Se llama `tests` y no `pruebas` para no confundirla con la rama `pruebas`.

## Qué va aquí

- `aislamiento/`: la prueba del intruso
- `esquema/`: tablas globales y auditoría de solo inserción
- `concurrencia/`: bloqueos simultáneos

Herramientas: `pytest`, `pytest-django` y `factory-boy` (§7.1).

## Con qué se conecta

- Con todas las apps. La prueba del intruso y la de tablas globales están en la Definition of Done (§5.4)
- Rama `desarrollo`: no se sube con pruebas en rojo (§8.5)
