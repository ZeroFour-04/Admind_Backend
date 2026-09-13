# conjuntos

Alcance: Núcleo (§3.1).

La copropiedad. Todo lo demás cuelga de un conjunto.

## Qué va aquí

- Modelo `Conjunto`, con baja lógica (`activo`) y doble confirmación escrita para desactivarlo: escribir el nombre exacto
- **Asistente de creación** (`conjunto.crear`, solo Superusuario). El conjunto no queda operativo hasta tener datos básicos, catálogo de áreas, al menos un usuario con rol Administración y reglamento cargado. Las reglas beta se configuran en el mismo asistente
- Cambio de **conjunto activo** (HU-26), que escribe en la sesión

## Con qué se conecta

- `apps/comun/aislamiento/`: lee de la sesión el conjunto activo que se fija aquí
- `apps/areas/`, `apps/reglas/`, `apps/permisos/`, `apps/documentos/`: el asistente las necesita completas antes de activar el conjunto
- Frontend: `Admind_Front-End/apps/conjuntos/`

## Referencias

Maestro §3.1, §5.4, §5.11 · HU-26

## Aplazado

`Conjunto.acento` no se implementa por ahora: se arranca con un solo acento (§6.3).
