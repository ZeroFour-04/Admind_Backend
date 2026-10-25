# infracciones

Alcance: Comprometido (§3.2).

El sistema **no sanciona**: notifica la infracción y registra su desenlace.

## Qué hay hoy

**Construido el 2026-10-25 (HU-30, rama `feat/infracciones-registro`, sin commit):** `RegistroDeInfraccion` (`infracciones/0001`) con los `CHECK` de abajo y FK compuestas; `servicios.registrar` (comunica a propietario y arrendatario y sella `fecha_notificacion` en la misma transacción; sin destinatarios, 400), `cerrar` (avisa otra vez, origen `infraccion.cierre`) y `anular` (sin aviso).

| Método | Ruta | Permiso | Respuestas |
|---|---|---|---|
| `GET` / `POST` | `/infracciones/` | `infraccion.ver` / `infraccion.registrar` | 200 con la lista (abiertos primero) · 201 · 400 |
| `GET` | `/infracciones/<id>/` | `infraccion.ver` | 200 · 404 |
| `POST` | `/infracciones/<id>/cierre/` | `infraccion.cerrar` | 200 · 409 si ya está cerrado o anulado |
| `POST` | `/infracciones/<id>/anulacion/` | `infraccion.anular` (solo el Superusuario) | 200 con motivo · 409 si ya está anulado |

Todos los permisos son sensibles (2FA). Ninguna ruta admite `PUT`, `PATCH` ni `DELETE`. Un registro anulado sigue en la lista.

## Diseño

- Modelo `RegistroDeInfraccion` (§5.8). Sin campo `estado`: está abierto si `cierre_fecha` es nulo
- `fecha_notificacion` obligatoria; la comunicación va a **propietario y arrendatario**, ambos
- Visibilidad solo para Administración y vínculos vigentes de la unidad

## Lo que no existe

Campos de sanción, multa o restricción de uso. No son permisos denegados: no existen (§4.2).

## Con qué se conecta

- `apps/unidades/`: la unidad y sus vínculos, que reciben la notificación
- `apps/casos/`: `caso_id` opcional
- `apps/notificaciones/`
- `apps/comun/modelos_base/`: un registro equivocado se anula, solo por el Superusuario
- Nunca con `apps/anuncios/`: una infracción no llega al tablón
- Frontend: `Admind_Front-End/apps/infracciones/`

## Referencias

Maestro §4.2, §5.8 · R11 · Decisión §9: 5
