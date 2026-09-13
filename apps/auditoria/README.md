# auditoria

Alcance: Núcleo (§3.1).

El registro de todo lo que pasa: quién, qué, cuándo, valor anterior y valor nuevo. Es de **solo inserción**, y eso no depende de que el código se porte bien.

## Qué va aquí

- Modelo del registro de auditoría
- Marca `via_superusuario` en toda acción del Superusuario
- El historial de los campos con historia, como la prioridad del triage
- La migración con `RunSQL` que le quita al usuario de aplicación `UPDATE` y `DELETE` sobre estas tablas (§7.2, punto 3)

## Con qué se conecta

- Todas las apps escriben aquí; `auditoria` no importa ninguna
- `bd/`: los privilegios suponen que existen dos usuarios de base
- `tests/esquema/`: comprueba que un `UPDATE` sobre auditoría falla
- Frontend: `Admind_Front-End/apps/auditoria/`

## Referencias

Maestro §5.3, §5.11, §7.2 · Decisiones §9: 20, 21, 26 · R10

## Pendiente

- ¿Se registran también las **consultas** del Superusuario a datos personales, o solo sus escrituras? (R10, §11.5)
- El Registro de actividades (§3.3, condicional) sería una vista sobre esta tabla, no una tabla nueva
