# conjuntos

Alcance: Núcleo (§3.1).

La copropiedad. Todo lo demás cuelga de un conjunto.

## Qué va aquí

- Modelo `Conjunto`, con baja lógica (`activo`) y doble confirmación escrita para desactivarlo: escribir el nombre exacto
- `acento`: uno de los ocho del catálogo cerrado (§6.3). Se guarda el slug; el frontend lo pone en `data-acento`
- **Asistente de creación** (HU-03), en `servicios.py`. `conjunto.crear` lo tienen el Superusuario y, desde el 2026-09-21, Administración del conjunto activo. Quien crea desde Administración queda como Administración del conjunto nuevo. El conjunto no queda operativo hasta tener datos básicos, catálogo de áreas, al menos un usuario con rol Administración, reglamento cargado y reglas beta
- Mientras no existan áreas, reglamento y reglas beta (HU-09, HU-33, HU-10), esos requisitos cuentan como no cumplidos: ningún conjunto puede quedar operativo todavía

## API

Todas exigen token y, con permisos sensibles, el segundo factor verificado (ver `apps/cuentas/README.md`). Las de `actual/` trabajan sobre el conjunto activo de la sesión: nunca reciben el conjunto como parámetro.

| Método | Ruta | Qué hace | Respuestas |
|---|---|---|---|
| `POST` | `/conjuntos/` | Paso 1: crea el conjunto con `nombre`, `direccion` y `acento`, y lo deja como conjunto activo. Exige `conjunto.crear` | 201 con `conjunto` y el estado de la sesión · 400 si el nombre ya existe o el acento no está en el catálogo |
| `GET` | `/conjuntos/actual/` | Resumen del asistente: datos, administradores, requisitos y si puede activarlo. Exige `conjunto.editar` | 200 |
| `PATCH` | `/conjuntos/actual/` | Guardado parcial de los datos básicos. Exige `conjunto.editar`, y `conjunto.branding` para cambiar el acento | 200 con el resumen |
| `POST` | `/conjuntos/actual/activar/` | Lo deja operativo si cumple los requisitos. Exige `conjunto.activar` | 200 · 400 con la lista de `faltantes` |

El paso 2 del asistente (administración) usa `POST /auth/usuarios/` con el rol `administracion`.

## Con qué se conecta

- `apps/comun/aislamiento/`: lee de la sesión el conjunto activo
- `apps/areas/`, `apps/reglas/`, `apps/permisos/`, `apps/documentos/`: el asistente las necesita completas antes de activar el conjunto
- Frontend: `Admind_Front-End/apps/conjuntos/`

## Referencias

Maestro §3.1, §5.4, §5.11, §6.3 · HU-03, HU-26

## Pendiente

- Auditoría de la creación (quién y cuándo): llega con `apps/auditoria/`
- ¿Administración también activa sus conjuntos? Hoy `conjunto.activar` es solo del Superusuario
