# unidades

Alcance: Núcleo (§3.1).

Las viviendas del conjunto y la posición jurídica de cada persona sobre ellas. Propietario y arrendatario **no son roles**: son vínculos.

## Qué va aquí

- Modelo de unidad (la vivienda), por conjunto
- Modelo `VinculoUnidad`: `tipo ∈ {propietario, arrendatario}`, `reside`, `vigencia_desde`, `vigencia_hasta`. Un vínculo que termina se cierra; no se borra
- **Enrutamiento por vínculos:** la consulta que responde a quién le llega un hecho según su naturaleza (§5.5)

## Qué hay hoy

Lo mínimo que necesita HU-25, construido el 2026-09-22. El resto es de HU-08.

- `Unidad` (nombre único en el conjunto) y `VinculoUnidad`, las dos con `ModeloDeConjunto`; el vínculo apunta a la unidad con FK compuesta
- `servicios.destinatarios(unidad, hecho)`: la tabla del §5.5 como consulta, más el anuncio dirigido a una vivienda (§5.7), que llega a todo vínculo vigente
- `GET /unidades/`: las unidades del conjunto activo, con `vinculo.gestionar` o `anuncio.dirigir`
- **No hay** pantalla ni API para crear unidades ni vínculos: eso es HU-08

## Con qué se conecta

- `apps/personas/`: el vínculo referencia a la persona global
- `apps/reservas/`: el derecho a reservar nace de un vínculo vigente con `reside = true`, no del rol
- `apps/notificaciones/`: le entrega los destinatarios ya resueltos
- `apps/anuncios/`, `apps/infracciones/`, `apps/parqueaderos/`, `apps/pagos/`: todas apuntan a una unidad
- Frontend: `Admind_Front-End/apps/unidades/`

## Referencias

Maestro §5.5 · Decisión §9: 10

## Pendiente

- De dónde sale `expensa_mensual` por unidad (§11.5)
