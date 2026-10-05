# anuncios

Alcance: Comprometido (§3.2).

El tablón del conjunto. Comunicación de una sola vía: sin respuesta, sin hilo, sin tiempo real.

## Qué va aquí

- Anuncio con uno de **dos alcances**: todo el conjunto o una vivienda
- Solo texto, o texto con **hasta 4 fotos** (`FotoDeAnuncio`, decisión de Alejo del 2026-10-05)
- Acuse de lectura como campo, no como bloqueo (§11.6). Sin construir

## API

| Método | Ruta | Qué hace | Respuestas |
|---|---|---|---|
| `GET` | `/anuncios/` | El tablón: quien publica ve todos; los demás, los de todo el conjunto y los de sus viviendas. Cada anuncio trae `fotos`: los ids en orden, o `[]` | 200 |
| `POST` | `/anuncios/` | Publica y avisa una sola vez. `alcance` `conjunto` exige `anuncio.publicar`; `vivienda` exige `anuncio.dirigir` y `unidad`. Con fotos va como `multipart/form-data`, con el campo `fotos` repetido (0 a 4 archivos); solo texto puede seguir yendo en JSON | 201 · 400 · 403 |
| `GET` `PATCH` | `/anuncios/<id>/` | Ver un anuncio; editar su `titulo` o `cuerpo` sin volver a avisar. Edita solo quien lo publicó. El alcance y las fotos no cambian: mandarlos responde 400 | 200 · 400 · 403 · 404 |
| `GET` | `/anuncios/<id>/fotos/<foto_id>/` | Los bytes de la foto con su `Content-Type` real. Solo para quien ve el anuncio | 200 · 404 |

Destinatarios: con alcance conjunto, toda persona con asignación vigente en él; con alcance vivienda, todo vínculo vigente de la unidad, resida o no. No hay borrado (decisión abierta, maestro §5.11).

## Fotos

- **Qué se acepta:** PNG, JPG o WebP de hasta 5 MB cada una. Decide la firma del archivo, no su nombre ni el tipo que declara el navegador (`tipo_real_de_imagen`, de `apps/conjuntos/`).
- **Tres capas:** el serializer cuenta las fotos; `servicios.tipos_de_las_fotos()` revisa cada una y levanta `FotoInvalida` (400 bajo `fotos`); la base guarda el tope con `UNIQUE (anuncio, orden)` y `CHECK (orden < 4)`.
- **Todo o nada:** con una foto que no sirve no se publica ni se avisa.
- **Quedan fijas:** se suben al publicar y no se agregan, cambian ni quitan después.
- **Nunca viajan en un listado:** van en su propia tabla y el tablón las precarga sin `contenido`.
- **El aviso no las lleva:** si el anuncio tiene fotos, el texto de la bandeja y del correo termina diciendo cuántas son.

## Lo que no va

El alcance "persona". Entre una vivienda y una persona está la frontera de lo que todavía se puede llamar anuncio (R14).

## Con qué se conecta

- `apps/unidades/`: el alcance "una vivienda" llega a todo vínculo vigente, residan o no
- `apps/notificaciones/`
- Nunca con `apps/infracciones/`
- Frontend: `Admind_Front-End/apps/anuncios/`

## Referencias

Maestro §5.7 · R14 · Decisión §9: 29 · HU-25
