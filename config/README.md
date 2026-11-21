# config

Proyecto de Django: el paquete que crea `django-admin startproject`. No contiene lógica de negocio.

## Qué va aquí

- Ajustes: conexión a PostgreSQL, apps instaladas, DRF, `django-otp`, middleware y archivos estáticos
- URLs raíz, que montan las URLs de cada app de `apps/`
- Arranque del servidor (WSGI/ASGI)

## Con qué se conecta

- `apps/`: registra cada app y monta sus rutas
- `apps/comun/aislamiento/`: su middleware se declara aquí, después del de sesión
- `bd/`: la aplicación se conecta con el usuario de aplicación, no con el dueño
- Variables de entorno: `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`,
  `CORS_ALLOWED_ORIGINS` (un solo origen del frontend: `http://127.0.0.1:8001` en local,
  `https://admind.detkor.com` en la nube),
  conexión a PostgreSQL (`DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`) y SMTP.
  Los secretos nunca se guardan en el repositorio (§7.1)

## Pendiente

- Qué usuario de base usa cada entorno y cómo crea `pytest-django` la base de pruebas (§11.5)
- Los ajustes del ambiente de pruebas: todavía no está definido (§11.5)
