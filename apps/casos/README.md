# casos

El residente crea un caso con título, descripción y una imagen opcional. La imagen se valida por firma y tamaño, y se almacena separada del registro del caso. La Secretaría clasifica (toma, prioriza, descarta por causal formal o redirige) y la Administración decide (responde o rechaza). Administración ve y atiende todos los casos, también los que nadie le redirigió: el sistema funciona con cero secretarías.

## El ciclo de un caso (HU-29)

| Estado | Quién lo produce | Sale hacia |
|---|---|---|
| `ABIERTO` (Por revisar) | El residente, al crearlo | `EN_REVISION`, `REDIRIGIDO`, `RECHAZADO`, `RESUELTO` |
| `EN_REVISION` | Quien lo toma (`caso.gestionar` o `caso.responder`). Es opcional | `REDIRIGIDO`, `RECHAZADO`, `RESUELTO` |
| `REDIRIGIDO` | Secretaría, con nota interna opcional | `RESUELTO`, `RECHAZADO` |
| `CITADO` | Nadie todavía: depende de Citas (HU-31) | `RESUELTO`, `RECHAZADO` |
| `RESUELTO` | Administración, con respuesta escrita obligatoria | Terminal |
| `RECHAZADO` | Secretaría (descarte: causal y motivo) o Administración (motivo) | Terminal |

Toda transición pasa por `servicios._pasar`: bloquea la fila, revisa el estado (si no sirve, `CasoNoGestionable` → 409), escribe, audita y avisa a quien abrió el caso, por la aplicación y por correo. La base no guarda un caso resuelto sin respuesta, uno rechazado sin motivo ni uno urgente sin justificación.

| Ruta | Nombre | Permiso |
|---|---|---|
| `GET /casos/` | `casos` | `caso.crear` (los propios) o `caso.ver_todos` (todos; `?ver=abiertos`, `?orden=antiguedad`) |
| `POST /casos/` | `casos` | `caso.crear` |
| `GET /casos/<id>/` | `caso-detalle` | `caso.ver_todos`, o `caso.crear` si es suyo; si no, 404 |
| `POST /casos/<id>/tomar/` | `caso-tomar` | `caso.gestionar` o `caso.responder` |
| `POST /casos/<id>/prioridad/` | `caso-prioridad` | `solicitud.priorizar` (`URGENTE` pide `justificacion`) |
| `POST /casos/<id>/redirigir/` | `caso-redirigir` | `caso.gestionar` (`nota` opcional) |
| `POST /casos/<id>/descartar/` | `caso-descartar` | `caso.gestionar` (`causal` y `motivo`) |
| `POST /casos/<id>/responder/` | `caso-responder` | `caso.responder` (`respuesta`) |
| `POST /casos/<id>/rechazar/` | `caso-rechazar` | `caso.responder` (`motivo`) |
| `GET /casos/<id>/fotos/<foto_id>/` | `caso-foto` | Quien puede ver el caso |

Para gestión el orden es: abiertos primero, por prioridad y luego antigüedad. `?orden=antiguedad` ignora la prioridad. El residente no recibe la nota de redirección, la justificación de la prioridad ni quién actuó.

Alcance: Comprometido (§3.2).

Los casos que abre un residente: algo que el conjunto tiene que atender y responder. La bandeja muestra el residente, su vivienda residencial vigente y la fecha de creación. Si se rechaza un caso, el motivo queda visible al residente al consultar el detalle.

## Qué va aquí

- Modelo de caso, con el contrato de triage de tres campos (§5.7)
- Respuesta obligatoria. Un rechazo formal cuenta como respuesta

## Con qué se conecta

- `apps/triage/`: aparece en la bandeja, por prioridad y luego antigüedad
- `apps/infracciones/`: un registro de infracción puede nacer de un caso
- `apps/notificaciones/`
- Frontend: `Admind_Front-End/apps/casos/`

## Referencias

Maestro §5.7, §5.8 · HU-29

## Pendiente

- Las causales de descarte (`CausalDeDescarte`) las fijó Alejo el 2026-10-13; falta validarlas con un administrador real (R13, §11.4)
- La vivienda no se guarda en el caso: se deduce de dónde reside hoy quien lo abrió
- `CITADO` no lo produce nada hasta que exista Citas (HU-31)
- ¿Reloj de vencimiento para casos? Hay que reevaluarlo (§11.6)
