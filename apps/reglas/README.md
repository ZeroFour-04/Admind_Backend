# reglas

Alcance: Núcleo (§3.1).

El motor de reglas: cada conjunto configura, a partir de su reglamento, qué reservas acepta. Es uno de los tres diferenciadores del proyecto (§1).

## Qué va aquí

- **Reglas del sistema** (`sistema.py`): en código; nadie las configura ni las apaga
- **Reglas alfa y beta** (`catalogo.py` y `Regla`): catálogo de **tipos parametrizados**, no un DSL. Una regla alfa es del conjunto y no lleva área; una beta es de un área. El nivel lo dice el catálogo, y cada tipo se define **una sola vez** (en el conjunto o en cada área)
- Cada regla = tipo + parámetros + vigencia + conjunto, y el área si es beta. Editar es versionar: la anterior se cierra y la nueva la reemplaza
- La **descripción fija** de cada tipo, que el front pide por `GET /reglas/catalogo/`
- `MODOS_POR_TIPO`: a qué modo de uso aplica cada tipo (`modos` en el catálogo). Definir una regla de área en un área de otro modo responde 400 bajo `area`. Si el área cambia de modo, `servicios.retirar_las_de_otro_modo` retira las que dejaron de aplicar
- `PARQUEADEROS_POR_VIVIENDA` (alfa): `{"carro", "moto", "bicicleta"}`, enteros desde 0 (0 = ninguno de ese vehículo). Sin modos: la lee `apps/parqueaderos` al asignar (HU-34, `reglas/0008`); sin regla definida, sin tope
- `ACOMPANANTES` (alfa): `{"maximo": entero desde 0}`, donde 0 es «no se permiten». Sin regla definida los acompañantes entran y el aforo es el único tope. La evalúa `apps/ingresos/`, no el evaluador de reservas
- `DIA_LIMITE_DE_PAGO` (alfa, `{"dia": 1 a 28}`, `MODOS_POR_TIPO` vacío): ningún evaluador la evalúa; la lee `apps/pagos/` para saber desde cuándo hay mora. `REQUIERE_PAZ_Y_SALVO` solo restringe si también está definida. Se construyó el 2026-10-10 (migración `0007`)
- `UNA_RESERVA_POR_DIA` y `SIN_FRANJAS_SEGUIDAS` (beta, solo áreas con reserva, sin parámetros): definirlas es activarlas. La primera cuenta las apartadas y reservadas del día en el área, de cualquier apartamento, y hace que `franjas()` deje de ofrecer las libres de ese día; la segunda mira la franja anterior y la siguiente del mismo apartamento
- Los tipos retirados (`AFORO`, `FRANJA_HORARIA`, `DIAS_NO_RESERVABLES`) siguen en el catálogo para leer el historial: no se crean ni se editan
- Evaluación en AND (todas restringen, así que no hay conflicto) y respuesta con **todas** las reglas que fallaron, no solo la primera. Orden: sistema, aforo del área, reglas del conjunto y reglas del área

## Con qué se conecta

- `apps/ingresos/`: tiene su propio evaluador y reutiliza `Resultado`, el catálogo y `reglas_vigentes`. Este módulo no importa `ingresos`
- `apps/reservas/`: evalúa las reglas cuando el residente envía la solicitud
- `apps/reservas/` también en el otro sentido: cuenta las solicitudes apartadas que caen en un día que el área no abre
- `apps/areas/`: las reglas beta son de un área, y el aforo que se evalúa siempre es `Area.aforo_maximo`
- `apps/unidades/`: la regla del sistema de residencia consulta vínculos
- `apps/pagos/`: la regla alfa «paz y salvo» pregunta por la mora en `mora.py`, que delega en `apps/pagos/mora.py` con un `import` tardío (dependencia circular: `pagos` lee reglas y `reglas` pregunta por pagos)
- `apps/conjuntos/`: las reglas se definen en el asistente de creación
- Frontend: `Admind_Front-End/apps/reglas/`

## Referencias

Maestro §5.10 · Decisión §9: 3. La definición vigente, del 2026-10-06, está en `05_Modulos/motor_reglas.md` de la documentación.

## Pendiente

- Cerrar el catálogo contra un reglamento real (§11.4, §11.5)
- Verificar lo legal de que *paz y salvo* restrinja por mora (`abiertas` 12.10 b): la regla ya restringe y se construyó sin haberlo verificado
