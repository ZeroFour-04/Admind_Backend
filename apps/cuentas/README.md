# cuentas

Alcance: Núcleo (§3.1).

`Usuario` y todo lo que protege la entrada: autenticación propia, recuperación de contraseña y 2FA TOTP.

## Qué va aquí

- Modelo `Usuario`: tabla global, sin `conjunto_id` (§5.4)
- Ingreso, salida y recuperación de contraseña
- 2FA TOTP con `django-otp`, **obligatorio para todo usuario con algún permiso sensible**
- Permiso de DRF que exige el 2FA verificado cuando la operación pide un permiso sensible (§7.2, punto 4)

## Con qué se conecta

- `apps/personas/`: los roles se asignan a personas, así que cada usuario corresponde a una
- `apps/permisos/`: de ahí sale si el usuario tiene permisos sensibles
- `apps/notificaciones/`: envía el correo de recuperación
- `apps/conjuntos/`: después de ingresar se elige el conjunto activo
- Frontend: `Admind_Front-End/apps/cuentas/`

## Referencias

Maestro §3.1, §5.3, §7.1, §7.2 · Sprint 1 (§11.2)

## Pendiente

- Sesión o token entre el servidor del frontend y esta API (§12.7 b)
