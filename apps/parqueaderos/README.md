# parqueaderos

Alcance: Comprometido (§3.2).

Los parqueaderos del conjunto y su asignación a un apartamento. Registra un hecho administrativo; no constituye un derecho.

## Qué va aquí

- **Construido el 2026-10-10 (HU-28, sin commit):** modelo `Parqueadero` (`codigo` único por conjunto y guardado en mayúsculas, `tipo ∈ {residentes, visitantes}`, `accesible`, `notas`, `activo`), su servicio (`parqueaderos()`, `crear`, `desactivar` con baja lógica) y la API: `GET` y `POST /parqueaderos/` y `POST /parqueaderos/<id>/desactivar/`
- Administra el catálogo `parqueadero.gestionar` (Administración). Lista quien tiene `parqueadero.ver`, `parqueadero.gestionar` o `visitante.registrar` (Vigilancia necesita los libres)
- Si está ocupado no lo dice por quién: `ocupado` sale de las visitas sin salida (`Visitante.parqueadero`, relación inversa `visitas`); esta app no importa `visitantes`. Un puesto con una visita sin salida no se retira (409)
- Pendiente de HU-34: modelo `AsignacionParqueadero`, una asignación vigente a la vez; cerrarla es poner `vigencia_hasta`
- Solo se asignarán los de tipo `residentes`

## Lo que no existe

- Asignar un parqueadero de visitantes a una unidad (§4.2)
- Quitarle el parqueadero a un residente moroso o como sanción

## Con qué se conecta

- `apps/unidades/`: se asigna a una unidad
- `apps/visitantes/`: la ocupación temporal de los de visitantes vive allá
- Frontend: `Admind_Front-End/apps/parqueaderos/`

## Referencias

Maestro §4.2, §5.6 · Decisión §9: 7
