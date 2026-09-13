# parqueaderos

Alcance: Comprometido (§3.2).

Los parqueaderos del conjunto y su asignación a un apartamento. Registra un hecho administrativo; no constituye un derecho.

## Qué va aquí

- Modelo `Parqueadero`: `codigo`, `tipo ∈ {residentes, visitantes}`, `accesible`, `notas`
- Modelo `AsignacionParqueadero`: una asignación vigente a la vez; cerrarla es poner `vigencia_hasta`
- Solo se asignan los de tipo `residentes`

## Lo que no existe

- Asignar un parqueadero de visitantes a una unidad (§4.2)
- Quitarle el parqueadero a un residente moroso o como sanción

## Con qué se conecta

- `apps/unidades/`: se asigna a una unidad
- `apps/visitantes/`: la ocupación temporal de los de visitantes vive allá
- Frontend: `Admind_Front-End/apps/parqueaderos/`

## Referencias

Maestro §4.2, §5.6 · Decisión §9: 7
