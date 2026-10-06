# unidades

Alcance: Núcleo (§3.1).

Las viviendas del conjunto y la posición jurídica de cada persona sobre ellas. Propietario y arrendatario **no son roles**: son vínculos.

## Qué va aquí

- Modelo de unidad (la vivienda: apartamento o casa), por conjunto, y de **agrupación** (torre, bloque, manzana), que es opcional
- El **generador de la estructura** (HU-39): describe el conjunto y crea sus viviendas en lote
- Modelo `VinculoUnidad`: `tipo ∈ {propietario, arrendatario}`, `reside`, `vigencia_desde`, `vigencia_hasta`. Un vínculo que termina se cierra; no se borra
- **Enrutamiento por vínculos:** la consulta que responde a quién le llega un hecho según su naturaleza (§5.5)

## Qué hay hoy

Lo mínimo que necesita HU-25, construido el 2026-09-22. El resto es de HU-08.

- `Unidad` (nombre único en el conjunto) y `VinculoUnidad`, las dos con `ModeloDeConjunto`; el vínculo apunta a la unidad con FK compuesta
- `servicios.destinatarios(unidad, hecho)`: la tabla del §5.5 como consulta, más el anuncio dirigido a una vivienda (§5.7), que llega a todo vínculo vigente
- `GET /unidades/`: las unidades del conjunto activo, con `vinculo.gestionar` o `anuncio.dirigir`
- Crear unidades y vínculos por la API (HU-08): `POST /unidades/`, `GET /unidades/<id>/`, `POST /unidades/<id>/vinculos/` y `POST …/vinculos/<id>/cerrar/`, con `vinculo.gestionar`

## Estructura de viviendas (HU-39, primera parte, 2026-10-06)

- `Agrupacion`: `etiqueta` (la palabra del conjunto), `nombre`, `clave` (los dos sin tildes ni mayúsculas, única en el conjunto), `tipo_vivienda` y `orden` de creación
- `Unidad` suma `tipo`, `agrupacion` (opcional, con FK compuesta), `numero` y `piso`. El `nombre` sigue siendo el texto completo ya armado: «Torre 1 – Apto 101»
- `estructura.py`: funciones puras. `generar(descripcion)` devuelve las viviendas de una tanda; no toca la base. Cuatro patrones: `piso_consecutivo`, `consecutivo`, `corrido` y `lista`
- `servicios.previsualizar_estructura()` y `generar_estructura()` usan ese mismo cálculo. Generar es todo o nada, omite las que ya existen y deja un registro `unidad.generar` en la auditoría

| Método | Ruta | Qué hace | Respuestas |
|---|---|---|---|
| `POST` | `/unidades/estructura/previsualizar/` | Lo que se crearía con esa descripción. No guarda | 200 · 400 · 409 si una agrupación existe con otro tipo de vivienda |
| `POST` | `/unidades/estructura/` | Crea las agrupaciones y viviendas que falten | 201 si creó algo, 200 si todo existía · 400 · 409 |
| `GET` | `/unidades/agrupaciones/` | Las agrupaciones con cuántas viviendas tiene cada una, las que no tienen agrupación y el total | 200 |

Las tres exigen `vinculo.gestionar`. `GET /unidades/` ordena por agrupación, piso y número. Lo registrado a mano queda como apartamento y sin agrupación.

## Con qué se conecta

- `apps/personas/`: el vínculo referencia a la persona global
- `apps/reservas/`: el derecho a reservar nace de un vínculo vigente con `reside = true`, no del rol
- `apps/notificaciones/`: le entrega los destinatarios ya resueltos
- `apps/anuncios/`, `apps/infracciones/`, `apps/parqueaderos/`, `apps/pagos/`: todas apuntan a una unidad
- Frontend: `Admind_Front-End/apps/unidades/`

## Referencias

Maestro §5.5 · Decisión §9: 10

## Pendiente

- Segunda parte de HU-39: registrar a mano dentro de una agrupación, renombrarla y retirar viviendas
- De dónde sale `expensa_mensual` por unidad (§11.5)
