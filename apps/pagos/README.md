# pagos

Alcance: Comprometido (§3.2).

Pago de la cuota de administración: el residente **reporta** y una persona **confirma**.

## Qué va aquí

- **Construido el 2026-10-10 (HU-35, sin commit):** `PagoDeAdministracion` (una fila por vivienda y mes, único en la base; guarda quién reportó, quién confirmó y cuándo, y el estado se calcula) y `Comprobante` (el archivo dentro de la base, con su tipo real y su SHA-256)
- `periodos.py` (meses, funciones puras), `servicios.py` (tabla del mes con buscador en el servidor, check idempotente con `select_for_update`, reporte con validación por firma, «mis pagos» y descarga por vínculo) y `mora.py`
- Cinco rutas bajo `/pagos/administracion/`: la tabla (`pago.ver`), el check (`pago.confirmar`), el reporte y «mios» (`pago.reportar`) y el comprobante. Ninguna fila trae la cédula
- **La mora** (`mora.py`): una vivienda está en mora si le falta el pago confirmado de algún mes vencido, contando desde el mes en que se definió por primera vez la regla `DIA_LIMITE_DE_PAGO`. Sin esa regla, nadie. `apps/reglas/mora.py` delega aquí con un `import` tardío
- Paz y salvo (la regla vive en `apps/reglas/`; aquí solo se responde si hay mora)

## Lo que no existe

- Pasarela de pagos: manejar dinero real implica PCI-DSS (§3.4)
- Monto, saldo, intereses ni sanciones: el sistema registra si el mes se pagó, no cuánto
- Restricción de uso por mora sobre bienes esenciales (§4.2)

## Con qué se conecta

- `apps/unidades/`: los vínculos vigentes dicen quién puede reportar (propietario o arrendatario, resida o no) y a quién muestra la tabla
- `apps/comun/archivos/`: la validación del comprobante por su firma, la misma de HU-16
- `apps/reglas/`: la regla alfa `DIA_LIMITE_DE_PAGO` (que lee este módulo) y la regla «paz y salvo» (que pregunta por la mora)
- Frontend: `Admind_Front-End/apps/pagos/`

## Referencias

Maestro §3.2, §3.4, §4.2, §5.5

## Pendiente

- Verificar lo legal de restringir por mora (`abiertas` 12.10 b): se construyó sin haberlo verificado
- Avisos por el canal de notificaciones y un documento de paz y salvo descargable
- La cuota mensual por unidad (§11.5), solo si algún día se necesita el monto
