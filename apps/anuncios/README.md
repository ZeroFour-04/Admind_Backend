# anuncios

Alcance: Comprometido (§3.2).

El tablón del conjunto. Comunicación de una sola vía: sin respuesta, sin hilo, sin tiempo real.

## Qué va aquí

- Anuncio con uno de **dos alcances**: todo el conjunto o una vivienda
- Acuse de lectura como campo, no como bloqueo (§11.6)

## API

| Método | Ruta | Qué hace | Respuestas |
|---|---|---|---|
| `GET` | `/anuncios/` | El tablón: quien publica ve todos; los demás, los de todo el conjunto y los de sus viviendas | 200 |
| `POST` | `/anuncios/` | Publica y avisa una sola vez. `alcance` `conjunto` exige `anuncio.publicar`; `vivienda` exige `anuncio.dirigir` y `unidad` | 201 · 400 · 403 |
| `GET` `PATCH` | `/anuncios/<id>/` | Ver un anuncio; editar su `titulo` o `cuerpo` sin volver a avisar. Edita solo quien lo publicó. El alcance no cambia | 200 · 400 · 403 · 404 |

Destinatarios: con alcance conjunto, toda persona con asignación vigente en él; con alcance vivienda, todo vínculo vigente de la unidad, resida o no. No hay borrado (decisión abierta, maestro §5.11).

## Lo que no va

El alcance "persona". Entre una vivienda y una persona está la frontera de lo que todavía se puede llamar anuncio (R14).

## Con qué se conecta

- `apps/unidades/`: el alcance "una vivienda" llega a todo vínculo vigente, residan o no
- `apps/notificaciones/`
- Nunca con `apps/infracciones/`
- Frontend: `Admind_Front-End/apps/anuncios/`

## Referencias

Maestro §5.7 · R14 · Decisión §9: 29 · HU-25
