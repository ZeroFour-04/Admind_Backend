# cuentas

Alcance: Núcleo (§3.1).

`Usuario` y todo lo que protege la entrada: autenticación propia, recuperación de contraseña y 2FA TOTP.

## Qué va aquí

- Modelo `Usuario`: tabla global, sin `conjunto_id` (§5.4)
- Sesión por token con registro en la base (`TokenDeSesion`, maestro §12.7 b): la base guarda solo la huella del token
- Ingreso, salida y recuperación de contraseña por correo
- Límite de enlaces de recuperación: 3 por hora por correo, con el throttling de DRF (`limites.py`). Se declara en la vista y cuenta en la memoria del proceso
- Selección del conjunto activo (HU-26)
- Creación de usuarios con un rol asignado en el conjunto activo
- 2FA TOTP con `django-otp`, **obligatorio para todo usuario con algún permiso sensible** (`dos_factores.py`)
- Permiso de DRF que exige el 2FA verificado a quien tenga permisos sensibles (`permisos.py`, §7.2 punto 4)
- Salida para quien perdió la aplicación de autenticación y los códigos de respaldo: un enlace de un solo uso al correo de la cuenta quita el 2FA y cierra sus sesiones; al volver a entrar se configura de nuevo (`dos_factores.py`). Lo pide solo quien ya entró con su contraseña, con un límite de 3 por hora por cuenta (`limites.py`)
- Comando solo para pruebas en local: `python manage.py crear_usuarios_prueba` crea un conjunto de prueba y un usuario por rol (`<rol>@example.com`), con la contraseña que se pide al ejecutarlo

## API

Todas las rutas exigen `Authorization: Token <token>`, salvo las marcadas *pública*. Con algún permiso sensible, además, el segundo factor verificado: sin él responden 403, salvo las marcadas *sin 2FA*.

| Método | Ruta | Qué hace | Respuestas |
|---|---|---|---|
| `POST` | `/auth/login/` | *Pública.* Inicia sesión con `correo` y `contrasena` | 200 con `token`, `vence_en`, `conjunto_activo`, `permisos` y `dos_factores` · 401 con un mensaje que no dice si el correo existe |
| `POST` | `/auth/logout/` | *Sin 2FA.* Cierra la sesión | 204 |
| `GET` | `/auth/conjuntos/` | Conjuntos donde puede operar: los de sus asignaciones vigentes; el Superusuario, todos los activos | 200 con `id`, `nombre`, `direccion`, `acento`, `logo` (huella o `null`) |
| `POST` | `/auth/conjunto-activo/` | Elige el conjunto activo (`conjunto`) | 200 con el estado de la sesión · 404 si no puede operar ahí |
| `GET` | `/auth/usuarios/` | Cuentas con algún rol en el conjunto activo. Exige `usuario.gestionar` | 200 con `roles` en el conjunto activo |
| `POST` | `/auth/usuarios/` | Crea persona, cuenta y rol en el conjunto activo. Exige `usuario.gestionar` | 201 · 400 si el documento o el correo ya existen · 403 sin conjunto activo |
| `GET` | `/auth/usuarios/<id>/` | Una cuenta del conjunto activo. Exige `usuario.gestionar` | 200 · 404 si no está en el conjunto activo |
| `POST` | `/auth/recuperar/` | *Pública.* Envía el enlace de recuperación a `correo` | 202 siempre, exista o no la cuenta · 429 al cuarto pedido en una hora para el mismo correo |
| `POST` | `/auth/recuperar/confirmar/` | *Pública.* Cambia la contraseña con `uid`, `token` y `contrasena`, y cierra las sesiones abiertas | 204 · 400 si el enlace no sirve o la contraseña no cumple las reglas |
| `POST` | `/auth/dos-factores/configurar/` | *Sin 2FA.* Genera el secreto y el QR | 200 con `qr`, `clave` y `enlace` · 409 si ya está configurado |
| `POST` | `/auth/dos-factores/activar/` | *Sin 2FA.* Confirma el secreto con el primer `codigo` | 200 con los 10 `codigos_de_respaldo` y el estado de la sesión · 400 si el código no sirve |
| `POST` | `/auth/dos-factores/verificar/` | *Sin 2FA.* Verifica un `codigo` de la aplicación o uno de respaldo | 200 con el estado de la sesión · 400 si el código no sirve |
| `POST` | `/auth/dos-factores/restablecer/` | *Sin 2FA.* Envía al correo de la cuenta el enlace que quita el segundo factor | 202 · 400 si no tiene uno configurado · 429 al cuarto pedido en una hora para la misma cuenta |
| `POST` | `/auth/dos-factores/restablecer/confirmar/` | *Pública.* Con `uid` y `token`, borra el segundo factor y los códigos de respaldo y cierra las sesiones abiertas | 204 · 400 si el enlace no sirve |

El **estado de la sesión** es `{conjunto_activo, permisos, dos_factores: {requerido, configurado, verificado}}`.

## Con qué se conecta

- `apps/personas/`: los roles se asignan a personas, así que cada usuario corresponde a una
- `apps/permisos/`: de ahí sale si el usuario tiene permisos sensibles
- `apps/conjuntos/`: después de ingresar se elige el conjunto activo
- Frontend: `Admind_Front-End/apps/cuentas/`

## Referencias

Maestro §3.1, §5.3, §7.1, §7.2 · HU-01, HU-02, HU-26

## Pendiente

- El correo de recuperación **no** pasa por el canal de notificaciones: el canal necesita un conjunto activo y deja el aviso en la bandeja, y aquí no hay sesión ni conjunto (decisión de Alejo, 2026-10-04)
- `send_mail` es síncrono y sin `try`: si el servidor de correo falla, `/auth/recuperar/` responde 500 solo cuando la cuenta existe
- El límite de enlaces vive en memoria: se pierde al reiniciar el servidor y no se comparte entre procesos
- `/auth/login/` no limita intentos de contraseña
- Quitar el segundo factor no deja registro en la auditoría: `apps/auditoria/` escribe en el conjunto activo y aquí no hay ninguno. Tampoco lo deja la recuperación de contraseña
- Con el enlace por correo, el segundo factor protege tanto como el buzón de la cuenta: quien lo controla puede cambiar la contraseña y después quitar el 2FA (decisión de Alejo, 2026-10-05)
