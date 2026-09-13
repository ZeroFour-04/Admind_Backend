# aislamiento

La prueba del intruso (§5.4): un conjunto no puede ver ni tocar lo de otro.

## Qué va aquí

- Un usuario del conjunto A pide un recurso de B por identificador → **404**
- La misma petición con el `conjunto_id` de B en la URL o en el cuerpo → rechazada
- Un listado con datos de A y B devuelve solo los de A

## Con qué se conecta

- `apps/comun/aislamiento/`: es lo que se pone a prueba
- Cada app nueva con datos por conjunto agrega aquí su caso

## Referencias

Maestro §5.4 · R6
