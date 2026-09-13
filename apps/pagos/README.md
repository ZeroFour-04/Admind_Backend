# pagos

Alcance: Comprometido (§3.2).

Pago de la cuota de administración: el residente **reporta** y una persona **confirma**.

## Qué va aquí

- Reporte de pago con comprobante
- Confirmación por parte de Administración
- Paz y salvo

## Lo que no existe

- Pasarela de pagos: manejar dinero real implica PCI-DSS (§3.4)
- Restricción de uso por mora sobre bienes esenciales (§4.2)

## Con qué se conecta

- `apps/unidades/`: el obligado es el **propietario**
- `apps/documentos/`: el comprobante
- `apps/reglas/`: la regla beta "requiere paz y salvo"
- `apps/notificaciones/`
- Frontend: `Admind_Front-End/apps/pagos/`

## Referencias

Maestro §3.2, §3.4, §4.2, §5.5

## Pendiente

- De dónde sale `expensa_mensual` por unidad (§11.5)
