# casos

El residente crea un caso con título, descripción y una imagen opcional. La imagen se valida por firma y tamaño, y se almacena separada del registro del caso. Secretaría puede rechazarlo indicando una razón o redirigirlo a Administración; Administración ve únicamente los casos redirigidos.

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

- Lista cerrada de causales formales de rechazo (R13, §11.4)
- ¿Reloj de vencimiento para casos? Hay que reevaluarlo (§11.6)
