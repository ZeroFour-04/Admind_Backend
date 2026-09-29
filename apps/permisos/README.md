# permisos

Alcance: Núcleo (§3.1).

Catálogo de permisos, los seis roles y la asignación de roles a personas por conjunto. El administrador **asigna**; no crea ni edita roles.

## Qué va aquí

- Catálogos de permisos y roles **fijos en código** (§5.3). No hay pantalla para editarlos
- Modelo `Asignacion (persona, rol, conjunto)`. `conjunto` nulo solo para Superusuario
- **Un solo rol vigente por persona y conjunto** (restricción `asignacion_un_rol_por_conjunto`).
  En otro conjunto puede tener otro. Para darle otro rol se **cambia**: se cierra el actual y se
  abre el nuevo en la misma transacción
- Permisos efectivos = los de su rol en el conjunto activo más los de plataforma. Sin denegaciones
- El Superusuario tiene todos los permisos del catálogo en cualquier conjunto; necesita elegir
  un conjunto activo para operar sobre sus datos
- Marca de **permisos sensibles**, que exigen 2FA
- **Nunca cero gobierno:** la comprobación y el cambio de roles ocurren en la misma transacción (§5.11)

## Lo que no existe

- Las operaciones que la ley prohíbe, como sancionar. No son permisos denegados: son operaciones inexistentes (§4.2)
- Un permiso de aprobación para Secretaría

## Con qué se conecta

- `apps/personas/`: a quién se le asigna
- `apps/cuentas/`: consulta los permisos sensibles para exigir 2FA
- Todas las apps: cada vista declara el permiso que exige
- `apps/auditoria/`: toda asignación y revocación queda registrada
- Frontend: no tiene app propia; la asignación de roles se hace desde `Admind_Front-End/apps/personas/`

## Referencias

Maestro §5.3, §5.11 · Decisiones §9: 8, 9, 22 · R5, R10
