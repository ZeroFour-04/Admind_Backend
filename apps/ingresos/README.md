# ingresos

Alcance: Núcleo (§3.1). Sin historia todavía.

El segundo modo de uso de una zona: con ingreso. Vigilancia registra a quien entra y nunca hay adentro más personas que el aforo. El primer modo, con reserva, es `apps/reservas/`.

## Qué va aquí

- Tabla `Ingreso` (de conjunto): área, persona, vivienda, acompañantes, estado (`ADENTRO`, `SALIO`, `VENCIDO`), entrada, salida prevista y salida. **No guarda el documento**, solo la referencia a la persona. Un registro rechazado no deja fila
- Restricciones en la base: un solo ingreso `ADENTRO` por persona (`ingreso_uno_abierto_por_persona`), salida prevista posterior a la entrada, salida vacía solo mientras está adentro, FK compuestas a `areas_area` y `unidades_unidad`
- `evaluador.py`: reglas del sistema (vive en esa vivienda; zona con ingreso, activa y sin mantenimiento; dentro del horario; sin otro ingreso abierto), aforo, y las reglas del conjunto y del área que aplican al ingreso (acompañantes, paz y salvo, días que no abre). Todas en AND y la respuesta trae todos los motivos
- `servicios.py`, sin HTTP: `registrar`, `registrar_salida`, `zonas`, `adentro`, `vencidos_de_hoy`, `historial`, `buscar_residente`, `dar_salida_a_vencidos`, `ocupacion`
- **El último cupo:** el aforo es una suma. `registrar` toma la fila del área con `select_for_update`, da salida a los vencidos, cuenta y, si cabe, inserta. Prueba en `tests/concurrencia/test_aforo_de_ingresos.py`
- **Salida automática al siguiente acceso**, sin procesos en segundo plano: toda lectura y toda acción empieza por `dar_salida_a_vencidos`, que pasa a `VENCIDO`, fija la hora prevista como salida y avisa al residente (`origen="ingreso"`). A Vigilancia no le llega correo: ve a quien venció en su pantalla
- Salida prevista = entrada más la permanencia del área, sin pasar de la hora de cierre. Queda guardada: cambiar la permanencia del área no la mueve

## La API

| Petición | Permiso | Respuesta |
|---|---|---|
| `GET /ingresos/zonas/` | `area.ver`, `area.gestionar`, `ingreso.registrar` o `ingreso.ver_historico` | 200: por zona activa con ingreso, el área, `adentro`, `cupos`, `abierta_ahora` y `motivo_cierre`. Solo conteos, sin nombres |
| `POST /ingresos/residentes/buscar/` | `ingreso.registrar` | 200 `[{persona, nombre, unidades}]` · 404 «No encontrado», exista o no la persona en otro conjunto. Cada búsqueda queda en la auditoría, sin el documento |
| `POST /ingresos/` | `ingreso.registrar` | 201 · 400 `{"motivos": [...]}` · 404 · 409 si el área no es con ingreso |
| `GET /ingresos/` | `ingreso.registrar` (`adentro`, `vencidos_hoy`) y `ingreso.ver_historico` (`historial`, con `?area=` y `?fecha=`; hoy por defecto) | 200 |
| `POST /ingresos/<id>/salida/` | `ingreso.registrar` | 200 · 404 · 409 si ya había salido |

Las vistas piden el permiso y nada más: no revisan el rol por nombre.

## Con qué se conecta

- `apps/areas/`: el modo de uso, la permanencia y el aforo
- `apps/reglas/`: catálogo, reglas vigentes, `Resultado` y `mora` (la paz y salvo no restringe hasta que exista pagos)
- `apps/unidades/`: `residentes_por_documento`, quién vive en el conjunto
- `apps/notificaciones/`: el aviso al residente al cumplirse el tiempo
- `apps/comun/bloqueo/`: traduce el choque del índice único a `RecursoOcupado`
- `apps/auditoria/`: `ingreso.registrar`, `ingreso.salida` e `ingreso.buscar_residente`
- Frontend: `Admind_Front-End/apps/ingresos/`

## Referencias

`05_Modulos/ingresos.md` y `07_Planes/hechos/Plan_Zonas_Con_Ingreso.md` de la documentación.

## Pendiente

- Lo legal de [abiertas] 12.10 b sin verificar: se construyó con salvaguardas (D3 a)
- El vínculo `habitante`: hasta que exista, la familia entra como acompañante de un titular
- Las reglas de piscina de la Ley 1209
