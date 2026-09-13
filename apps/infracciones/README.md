# infracciones

Alcance: Comprometido (§3.2).

El sistema **no sanciona**: notifica la infracción y registra su desenlace.

## Qué va aquí

- Modelo `RegistroDeInfraccion` (§5.8). Sin campo `estado`: está abierto si `cierre_fecha` es nulo
- `fecha_notificacion` obligatoria; la comunicación va a **propietario y arrendatario**, ambos
- Visibilidad solo para Administración, Consejo y vínculos vigentes de la unidad

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
