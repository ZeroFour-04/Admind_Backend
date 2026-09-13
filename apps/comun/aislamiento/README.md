# aislamiento

La pieza técnica número 1 de §7.2: que un conjunto nunca vea los datos de otro, sin depender de que cada consulta se acuerde de filtrar.

## Qué va aquí

- **Middleware** que resuelve el conjunto activo desde la sesión y lo deja como contexto de solo lectura
- **Manager base** que agrega `WHERE conjunto_id = <conjunto activo>` a toda consulta. Nada de SQL crudo fuera de aquí
- El rechazo de toda petición que traiga `conjunto_id` en la URL o en el cuerpo
- Búsqueda por identificador siempre junto con el conjunto: si no aparece, **404, no 403**

## Con qué se conecta

- `config/`: el middleware se declara en los ajustes
- Todas las apps con datos por conjunto usan su manager
- `apps/conjuntos/`: el cambio de conjunto activo (HU-26) escribe en la sesión que este middleware lee
- `tests/aislamiento/`: la prueba del intruso comprueba que esto funciona

## Referencias

Maestro §5.4, §7.2 (punto 1) · R6 · Decisión §9: 14

## Pendiente

- Cómo llega la sesión del usuario cuando quien llama a la API es el servidor del frontend y no el navegador (§12.7 b)
