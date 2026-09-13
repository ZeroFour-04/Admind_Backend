# config

Proyecto de Django: el paquete que crea `django-admin startproject`. No contiene lógica de negocio.

## Qué va aquí

- Ajustes: conexión a PostgreSQL, apps instaladas, DRF, `django-otp`, middleware
- URLs raíz, que montan las URLs de cada app de `apps/`
- Arranque del servidor (WSGI/ASGI)

## Con qué se conecta

- `apps/`: registra cada app y monta sus rutas
- `apps/comun/aislamiento/`: su middleware se declara aquí, después del de sesión
- `bd/`: la aplicación se conecta con el usuario de aplicación, no con el dueño
- Variables de entorno: contraseñas de la base y del SMTP. Nunca en el repositorio (§7.1)

## Pendiente

- Qué usuario de base usa cada entorno y cómo crea `pytest-django` la base de pruebas (§11.5)
- Los ajustes del ambiente de pruebas: todavía no está definido (§11.5)
