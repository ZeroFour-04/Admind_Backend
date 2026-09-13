# comun

Infraestructura del Núcleo. No es un módulo del producto y no tiene pantalla: guarda los mecanismos que comparten todas las apps, para que existan una sola vez.

## Qué va aquí

- `aislamiento/`: conjunto activo y filtro obligatorio por `conjunto_id`
- `bloqueo/`: bloqueo exclusivo con transacción, compartido por reservas, citas y parqueadero de visitantes
- `modelos_base/`: campos y comportamiento que repite toda entidad (UUID, conjunto, anulación, baja lógica)

## Con qué se conecta

Con todas las apps de `apps/`. `comun` no importa ninguna de ellas.

## Referencias

Maestro §5.4, §5.11, §7.2 · Decisiones §9: 2, 14, 16, 21 · R1, R6
