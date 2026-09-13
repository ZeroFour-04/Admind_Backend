# apps

Una app de Django por módulo del producto. Cada módulo es dueño de sus modelos, sus reglas y sus endpoints.

## Forma de cada app, cuando haya código

`models.py`, `serializers.py`, `views.py`, `urls.py`, `migrations/` y sus pruebas unitarias. Las carpetas internas se crean cuando se necesiten, no antes.

## Con qué se conecta

- `config/`: registra cada app y monta sus URLs
- `apps/comun/`: toda app con datos por conjunto hereda sus modelos base y su manager filtrado
- `apps/permisos/`: toda vista declara qué permiso exige
- `apps/auditoria/`: toda escritura deja registro ahí
- Frontend: cada app tiene su pareja con el mismo nombre en `Admind_Front-End/apps/`, salvo `comun` y `permisos`

## Una regla de dependencias

`comun` y `auditoria` no importan ninguna app de negocio: todas las demás las usan a ellas.
