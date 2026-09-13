# reglas

Alcance: Núcleo (§3.1).

El motor de reglas: cada conjunto configura, a partir de su reglamento, qué reservas acepta. Es uno de los tres diferenciadores del proyecto (§1).

## Qué va aquí

- **Reglas alfa:** en código; el administrador no las desactiva
- **Reglas beta:** catálogo de **tipos parametrizados**, no un DSL. Cada regla = tipo + parámetros + área + vigencia + conjunto
- Evaluación en AND (todas restringen, así que no hay conflicto) y respuesta con **todas** las reglas que fallaron, no solo la primera

## Con qué se conecta

- `apps/reservas/`: evalúa las reglas cuando el residente envía la solicitud
- `apps/areas/`: las reglas beta se configuran por área
- `apps/unidades/`: la regla alfa de residencia consulta vínculos
- `apps/pagos/`: la regla beta "requiere paz y salvo"
- `apps/conjuntos/`: las reglas beta se cargan en el asistente de creación
- Frontend: `Admind_Front-End/apps/reglas/`

## Referencias

Maestro §5.10 · Decisión §9: 3

## Pendiente

- Cerrar la lista de reglas alfa y el catálogo beta contra un reglamento real (§11.4, §11.5)
- Vigencia y versionado: ¿snapshot de la versión aplicada en cada decisión? (§5.10)
