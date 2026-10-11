# visitantes

Alcance: Comprometido (§3.2).

La minuta de portería: entrada y salida de visitantes, y la ocupación temporal del parqueadero de visitantes.

## Qué va aquí

- Registro de visita con finalidad declarada, autorización y plazo de retención (Ley 1581)
- **Capa de servicio (2026-10-10, HU-28):** `servicios.py` guarda las reglas que antes estaban en la vista: solo Vigilancia registra (`exigir_vigilancia`, y lo mismo para la salida), el apartamento debe existir en el conjunto, y registro y salida dejan fila en la auditoría (`visitante.registrar`, `visitante.salida`)
- **Salida:** `Visitante.hora_salida` y `salida_registrada_por`; `POST /visitantes/<id>/salida/` (409 si ya salió). Quien solo registra ve las visitas de hoy **y** las que siguen adentro de días anteriores
- Ocupación temporal de un parqueadero de visitantes: pertenece a la visita (`Visitante.parqueadero`) y termina al registrar la salida. Un índice único parcial `(conjunto, parqueadero)` donde `hora_salida IS NULL` lo decide, tomado con `bloqueo.tomar`; si otra visita lo ocupó antes, 409 y la visita no queda registrada
- Pendiente: liberación manual por Vigilancia sin salida y listado de ocupaciones abiertas de más de N horas (§11.6)

## Lo que no va

- Retener el documento físico del visitante (§4.2)
- Convertir a un visitante recurrente en `Persona`: es un registro de portería con su propia purga (§11.6)

## Con qué se conecta

- `apps/comun/bloqueo/`: el parqueadero de visitantes es un recurso limitado (R1)
- `apps/parqueaderos/`: de ahí salen los parqueaderos de tipo `visitantes`
- `apps/unidades/` y `apps/notificaciones/`: avisar a quienes residen en la unidad visitada
- Frontend: `Admind_Front-End/apps/visitantes/`

## Referencias

Maestro §4.2, §5.5, §5.6, §11.6 · R1, R2

## Pendiente

- Plazo de retención y purga, y justificación escrita de la captura de documento (R2, §11.5)
