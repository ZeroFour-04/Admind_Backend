"""Pruebas de HU-11 (franjas y bloqueo de 3 minutos), HU-12 (avisos) y HU-13 (envío y reglas).

La concurrencia (N residentes sobre la misma franja) va en `tests/concurrencia/test_bloqueo_de_franjas.py`.
"""
import uuid
from datetime import datetime, time, timedelta

import pytest
from django.utils import timezone
from django.utils.formats import date_format
from rest_framework.test import APIClient

from apps.areas.models import Area
from apps.auditoria.models import Registro
from apps.comun.aislamiento.contexto import usar_conjunto
from apps.conjuntos.models import Conjunto
from apps.cuentas.models import TokenDeSesion, Usuario
from apps.notificaciones.models import Notificacion
from apps.permisos.catalogo import Rol
from apps.permisos.models import Asignacion
from apps.personas.models import Persona, TipoDocumento
from apps.reglas import mora
from apps.reglas.models import Regla
from apps.reservas.models import Solicitud
from apps.reservas.servicios import avisos
from apps.unidades.models import TipoVinculo, Unidad, VinculoUnidad

pytestmark = pytest.mark.django_db

CONTRASENA = "una-clave-larga-2026"
MANANA = timezone.localdate() + timedelta(days=1)
MANANA_EN_LETRAS = date_format(MANANA, r"l j \d\e F \d\e Y").lower()


def crear_usuario(correo, nombres, rol, conjunto):
    persona = Persona.objects.create(
        tipo_documento=TipoDocumento.CC,
        numero_documento=str(Persona.objects.count() + 1023456789),
        nombres=nombres,
        apellidos="Gómez",
    )
    Asignacion.objects.create(persona=persona, rol=rol, conjunto=conjunto)
    Usuario.objects.create_user(correo, CONTRASENA, persona)
    return persona


def cliente_para(correo):
    """Sesión con el segundo factor dado por verificado: su flujo se prueba en cuentas."""
    cliente = APIClient()
    respuesta = cliente.post("/auth/login/", {"correo": correo, "contrasena": CONTRASENA}, format="json")
    cliente.credentials(HTTP_AUTHORIZATION=f"Token {respuesta.json()['token']}")
    TokenDeSesion.objects.filter(usuario__correo=correo).update(dos_factores_verificado=True)
    return cliente


def vecino(conjunto, correo, nombres, unidad, reside=True, tipo=TipoVinculo.ARRENDATARIO):
    """Un residente con vínculo vigente sobre la unidad."""
    persona = crear_usuario(correo, nombres, Rol.RESIDENTE, conjunto)
    with usar_conjunto(conjunto.id):
        VinculoUnidad.objects.create(persona=persona, unidad=unidad, tipo=tipo, reside=reside)
    return cliente_para(correo)


def crear_area(conjunto, nombre, **extra):
    datos = {
        "hora_apertura": time(8), "hora_cierre": time(22), "duracion_franja_minutos": 240, "aforo_maximo": 50, **extra,
    }
    with usar_conjunto(conjunto.id):
        return Area.objects.create(nombre=nombre, **datos)


@pytest.fixture
def torres():
    return Conjunto.objects.create(nombre="Torres del Río")


@pytest.fixture
def apartamentos(torres):
    with usar_conjunto(torres.id):
        return Unidad.objects.create(nombre="Torre 1 – 101"), Unidad.objects.create(nombre="Torre 1 – 102")


@pytest.fixture
def salon(torres):
    return crear_area(torres, "Salón comunal")


@pytest.fixture
def pedro(torres, apartamentos):
    return vecino(torres, "pedro@correo.com", "Pedro", apartamentos[0])


@pytest.fixture
def lucia(torres, apartamentos):
    return vecino(torres, "lucia@correo.com", "Lucía", apartamentos[1])


def tomar(cliente, area, hora="08:00", fecha=MANANA):
    return cliente.post("/reservas/solicitudes/", {"area": str(area.id), "fecha": str(fecha), "hora_inicio": hora}, format="json")


def franjas(cliente, area, fecha=MANANA):
    respuesta = cliente.get("/reservas/franjas/", {"area": str(area.id), "fecha": str(fecha)})
    return {franja["hora_inicio"]: franja["estado"] for franja in respuesta.json()["franjas"]}


def solicitud(torres, solicitud_id):
    with usar_conjunto(torres.id):
        return Solicitud.objects.get(pk=solicitud_id)


# Criterios de aceptación


def test_franja_libre_y_reservar_deja_la_solicitud_en_tramite_con_3_minutos(pedro, torres, salon):
    antes = timezone.now()

    respuesta = tomar(pedro, salon)

    datos = respuesta.json()
    assert respuesta.status_code == 201
    assert (datos["estado"], datos["hora_inicio"], datos["hora_fin"]) == ("EN_SOLICITUD", "08:00", "12:00")
    vence = solicitud(torres, datos["id"]).bloqueo_vence_en
    assert antes + timedelta(minutes=3) <= vence <= timezone.now() + timedelta(minutes=3)
    assert 170 <= datos["segundos_restantes"] <= 180
    assert [unidad["nombre"] for unidad in datos["unidades_para_solicitar"]] == ["Torre 1 – 101"]


def test_otra_persona_sobre_una_franja_en_tramite_recibe_el_aviso_de_inmediato(pedro, lucia, salon):
    tomar(pedro, salon)

    respuesta = tomar(lucia, salon)

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == "Otra persona está tramitando esta franja en este momento."


def test_un_bloqueo_vencido_expira_al_siguiente_acceso_y_la_franja_queda_libre(pedro, lucia, torres, salon):
    en_tramite = tomar(pedro, salon).json()
    with usar_conjunto(torres.id):
        Solicitud.objects.filter(pk=en_tramite["id"]).update(bloqueo_vence_en=timezone.now() - timedelta(seconds=1))

    estados = franjas(lucia, salon)

    assert estados["08:00"] == "libre"
    assert solicitud(torres, en_tramite["id"]).estado == "EXPIRADA"


def test_con_un_bloqueo_activo_no_se_toma_otro_en_ninguna_area(pedro, torres, salon):
    piscina = crear_area(torres, "Piscina")
    primero = tomar(pedro, salon).json()

    respuesta = tomar(pedro, piscina)

    assert respuesta.status_code == 409
    assert respuesta.json()["solicitud"] == primero["id"]


def test_al_cerrar_el_formulario_el_bloqueo_se_libera_sin_esperar(pedro, lucia, torres, salon):
    en_tramite = tomar(pedro, salon).json()

    respuesta = pedro.post(f"/reservas/solicitudes/{en_tramite['id']}/liberar/")

    assert respuesta.status_code == 200
    assert (respuesta.json()["estado"], respuesta.json()["motivo_liberacion"]) == ("LIBERADA", "voluntaria")
    assert franjas(lucia, salon)["08:00"] == "libre"
    assert pedro.post(f"/reservas/solicitudes/{en_tramite['id']}/liberar/").status_code == 409
    assert solicitud(torres, en_tramite["id"]).estado == "LIBERADA"


def test_un_area_en_mantenimiento_no_admite_solicitudes(pedro, torres):
    """Criterio de HU-09."""
    gimnasio = crear_area(torres, "Gimnasio", en_mantenimiento=True)

    respuesta = tomar(pedro, gimnasio)

    assert respuesta.status_code == 409
    assert set(franjas(pedro, gimnasio).values()) == {"no_disponible"}


def test_un_propietario_que_no_vive_ahi_no_puede_reservar(torres, apartamentos, salon):
    """Criterio de HU-08: solo con un vínculo `reside = false`."""
    duena = vecino(torres, "marta@correo.com", "Marta", apartamentos[0], reside=False, tipo=TipoVinculo.PROPIETARIO)

    respuesta = tomar(duena, salon)

    assert respuesta.status_code == 400
    assert respuesta.json()["detail"] == "Para reservar necesitas vivir en un apartamento del conjunto."


# Reglas de las franjas


def test_cada_quien_ve_la_suya_como_propia_y_la_ajena_sin_saber_de_quien_es(pedro, lucia, salon):
    tomar(pedro, salon)

    respuesta = lucia.get("/reservas/franjas/", {"area": str(salon.id), "fecha": str(MANANA)})

    assert franjas(pedro, salon) == {"08:00": "propia", "12:00": "libre", "16:00": "libre"}
    assert franjas(lucia, salon)["08:00"] == "en_solicitud"
    assert "Pedro" not in respuesta.content.decode() and "persona" not in respuesta.content.decode()


def test_una_franja_que_ya_empezo_no_se_toma(pedro, torres):
    madrugada = crear_area(torres, "Cancha", hora_apertura=time(0), hora_cierre=time(23), duracion_franja_minutos=120)
    hoy = timezone.localdate()

    assert tomar(pedro, madrugada, "00:00", hoy).status_code == 400
    assert franjas(pedro, madrugada, hoy)["00:00"] == "pasada"
    assert tomar(pedro, madrugada, "08:30").status_code == 400  # no es el inicio de ninguna franja


def test_las_reservas_respetan_el_horario_de_apertura_y_cierre(pedro, torres):
    area = crear_area(
        torres, "Gimnasio", hora_apertura=time(10), hora_cierre=time(18), duracion_franja_minutos=120
    )

    respuesta_franjas = pedro.get("/reservas/franjas/", {"area": str(area.id), "fecha": str(MANANA)})

    assert [
        (franja["hora_inicio"], franja["hora_fin"]) for franja in respuesta_franjas.json()["franjas"]
    ] == [("10:00", "12:00"), ("12:00", "14:00"), ("14:00", "16:00"), ("16:00", "18:00")]
    assert tomar(pedro, area, "08:00").status_code == 400
    assert tomar(pedro, area, "18:00").status_code == 400
    reserva = tomar(pedro, area, "16:00")
    assert reserva.status_code == 201
    assert reserva.json()["hora_fin"] == "18:00"


def test_solo_se_ven_las_solicitudes_propias(pedro, lucia, salon):
    de_pedro = tomar(pedro, salon).json()

    assert [s["id"] for s in pedro.get("/reservas/solicitudes/").json()] == [de_pedro["id"]]
    assert lucia.get("/reservas/solicitudes/").json() == []
    assert lucia.get(f"/reservas/solicitudes/{de_pedro['id']}/").status_code == 404
    assert lucia.post(f"/reservas/solicitudes/{de_pedro['id']}/liberar/").status_code == 404


def test_sin_reserva_solicitar_no_se_toma_el_bloqueo(torres, salon):
    crear_usuario("vigilante@torres.com", "Carlos", Rol.VIGILANCIA, torres)
    vigilancia = cliente_para("vigilante@torres.com")

    assert tomar(vigilancia, salon).status_code == 403
    assert franjas(vigilancia, salon)["08:00"] == "libre"


# Avisos del panel de confirmación (HU-12)


def en_tramite(torres, area, persona, inicio, **extra):
    """Una solicitud EN_SOLICITUD que empieza en ese momento, creada directo en la base."""
    inicio = timezone.localtime(inicio)
    with usar_conjunto(torres.id):
        return Solicitud.objects.create(
            area=area, persona=persona, fecha=inicio.date(), hora_inicio=inicio.time().replace(microsecond=0),
            hora_fin=time.max, bloqueo_vence_en=timezone.now() + timedelta(minutes=3), **extra,
        )


def avisos_de(torres, solicitud):
    with usar_conjunto(torres.id):
        return avisos(solicitud)


@pytest.fixture
def ana(torres):
    return crear_usuario("ana@correo.com", "Ana", Rol.RESIDENTE, torres)


def test_se_avisa_si_la_franja_empieza_en_menos_de_24_horas(torres, salon, ana):
    pronto = en_tramite(torres, salon, ana, timezone.now() + timedelta(hours=2))
    lejos = en_tramite(torres, crear_area(torres, "Piscina"), crear_usuario("b@c.com", "Beto", Rol.RESIDENTE, torres),
                       timezone.now() + timedelta(days=3))

    assert avisos_de(torres, pronto) == ["menos_de_24h"]
    assert avisos_de(torres, lejos) == []


def test_se_avisa_si_la_fecha_es_el_ultimo_dia_de_la_anticipacion_maxima(torres, salon, ana):
    with usar_conjunto(torres.id):
        Regla.objects.create(tipo="ANTICIPACION_MAXIMA", parametros={"dias": 30}, creada_por=ana)
    ultimo_dia = timezone.make_aware(datetime.combine(timezone.localdate() + timedelta(days=30), time(10)))

    solicitud = en_tramite(torres, salon, ana, ultimo_dia)

    assert avisos_de(torres, solicitud) == ["limite_de_anticipacion"]


def test_se_avisa_si_ya_tiene_otra_solicitud_apartada_o_reservada(torres, salon, ana, apartamentos):
    piscina = crear_area(torres, "Piscina")
    en_tramite(torres, piscina, ana, timezone.now() + timedelta(days=5), estado="APARTADA", unidad=apartamentos[0])
    with usar_conjunto(torres.id):
        Solicitud.objects.filter(persona=ana).update(bloqueo_vence_en=timezone.now())

    solicitud = en_tramite(torres, salon, ana, timezone.now() + timedelta(days=3))

    assert avisos_de(torres, solicitud) == ["otra_solicitud"]


def test_el_detalle_trae_los_avisos_y_no_impiden_nada(pedro, salon):
    manana_temprano = tomar(pedro, salon).json()

    assert "avisos" in manana_temprano
    assert pedro.get(f"/reservas/solicitudes/{manana_temprano['id']}/").json()["avisos"] == manana_temprano["avisos"]


# Envío de la solicitud y motor de reglas (HU-13)


@pytest.fixture
def administracion(torres):
    """Dos personas con Administración vigente y una con Secretaría, que no debe recibir el aviso."""
    return [
        crear_usuario("admin1@torres.com", "Andrés", Rol.ADMINISTRACION, torres),
        crear_usuario("admin2@torres.com", "Sofía", Rol.ADMINISTRACION, torres),
        crear_usuario("secretaria@torres.com", "Carlos", Rol.SECRETARIA, torres),
    ]


def regla(torres, area, tipo, parametros, autor):
    """`area` va en `None` si la regla es del conjunto."""
    with usar_conjunto(torres.id):
        return Regla.objects.create(area=area, tipo=tipo, parametros=parametros, creada_por=autor)


def poner_aforo(torres, area, maximo):
    with usar_conjunto(torres.id):
        Area.objects.filter(pk=area.pk).update(aforo_maximo=maximo)


def enviar(cliente, solicitud_id, unidad, asistentes=20, **extra):
    datos = {"unidad": str(unidad.id), "motivo": "Cumpleaños", "asistentes": asistentes, **extra}
    return cliente.post(f"/reservas/solicitudes/{solicitud_id}/enviar/", datos, format="json")


def test_una_solicitud_valida_queda_apartada_y_se_avisa_a_la_administracion(
    pedro, torres, salon, apartamentos, administracion
):
    en_tramite = tomar(pedro, salon).json()

    respuesta = enviar(pedro, en_tramite["id"], apartamentos[0])

    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "APARTADA" and respuesta.json()["enviada_en"]
    with usar_conjunto(torres.id):
        avisados = sorted(n.persona.nombres for n in Notificacion.objects.filter(referencia=en_tramite["id"]))
        aviso = Notificacion.objects.filter(referencia=en_tramite["id"]).first()
    assert avisados == ["Andrés", "Sofía"]
    assert aviso.titulo == "Nueva solicitud de reserva"
    assert f"Salón comunal el {MANANA_EN_LETRAS}" in aviso.cuerpo


def test_secretaria_consulta_solicitudes_del_area_y_puede_aceptar_con_motivo(
    torres, salon, pedro, lucia, apartamentos, administracion
):
    enviada = enviar(pedro, tomar(pedro, salon).json()["id"], apartamentos[0]).json()
    secretaria = cliente_para("secretaria@torres.com")

    listado = secretaria.get(f"/reservas/areas/{salon.id}/solicitudes/")

    assert listado.status_code == 200
    assert len(listado.json()) == 1
    assert listado.json()[0]["residente"]["nombre"] == "Pedro Gómez"
    assert listado.json()[0]["motivo"] == "Cumpleaños"

    respuesta = secretaria.post(
        f"/reservas/solicitudes/{enviada['id']}/decision/",
        {"decision": "RESERVADA", "motivo": "Aforo y horario verificados."},
        format="json",
    )

    assert respuesta.status_code == 200
    assert (respuesta.json()["estado"], respuesta.json()["motivo_decision"]) == (
        "RESERVADA", "Aforo y horario verificados."
    )
    assert franjas(pedro, salon)["08:00"] == "propia"
    assert franjas(lucia, salon)["08:00"] == "reservada"
    with usar_conjunto(torres.id):
        guardada = Solicitud.objects.get(pk=enviada["id"])
        registro = Registro.objects.get(accion="reserva.aprobar", entidad_id=enviada["id"])
    assert guardada.decidida_por.nombres == "Carlos"
    assert guardada.decidida_en is not None
    assert registro.despues == {"estado": "RESERVADA", "motivo": "Aforo y horario verificados."}


def test_rechazar_solicitud_requiere_motivo_y_libera_la_franja(
    torres, salon, pedro, lucia, apartamentos, administracion
):
    enviada = enviar(pedro, tomar(pedro, salon).json()["id"], apartamentos[0]).json()
    secretaria = cliente_para("secretaria@torres.com")

    sin_motivo = secretaria.post(
        f"/reservas/solicitudes/{enviada['id']}/decision/",
        {"decision": "RECHAZADA", "motivo": "   "},
        format="json",
    )
    rechazada = secretaria.post(
        f"/reservas/solicitudes/{enviada['id']}/decision/",
        {"decision": "RECHAZADA", "motivo": "No se adjuntó el soporte requerido."},
        format="json",
    )

    assert sin_motivo.status_code == 400
    assert rechazada.status_code == 200
    assert (rechazada.json()["estado"], rechazada.json()["motivo_decision"]) == (
        "RECHAZADA", "No se adjuntó el soporte requerido."
    )
    assert franjas(lucia, salon)["08:00"] == "libre"


def test_no_se_puede_decidir_dos_veces_ni_consultar_solicitudes_de_otro_area(
    torres, salon, pedro, apartamentos, administracion
):
    enviada = enviar(pedro, tomar(pedro, salon).json()["id"], apartamentos[0]).json()
    secretaria = cliente_para("secretaria@torres.com")
    otra_area = crear_area(torres, "Piscina")

    assert secretaria.get(f"/reservas/areas/{otra_area.id}/solicitudes/").json() == []
    decision = {"decision": "RESERVADA", "motivo": "Aprobada."}
    assert secretaria.post(f"/reservas/solicitudes/{enviada['id']}/decision/", decision, format="json").status_code == 200
    repetida = secretaria.post(
        f"/reservas/solicitudes/{enviada['id']}/decision/",
        {"decision": "RECHAZADA", "motivo": "Cambio de opinión."},
        format="json",
    )
    assert repetida.status_code == 409


def test_bandeja_general_lista_solicitudes_enviadas_aceptadas_y_rechazadas(
    torres, salon, pedro, lucia, apartamentos, administracion
):
    secretaria = cliente_para("secretaria@torres.com")
    aceptada = enviar(pedro, tomar(pedro, salon, "08:00").json()["id"], apartamentos[0]).json()
    assert secretaria.post(
        f"/reservas/solicitudes/{aceptada['id']}/decision/",
        {"decision": "RESERVADA", "motivo": "Horario aprobado."},
        format="json",
    ).status_code == 200

    enviada = enviar(lucia, tomar(lucia, salon, "12:00").json()["id"], apartamentos[1]).json()
    assert secretaria.post(
        f"/reservas/solicitudes/{enviada['id']}/decision/",
        {"decision": "RECHAZADA", "motivo": "Falta autorización."},
        format="json",
    ).status_code == 200
    otra_enviada = enviar(pedro, tomar(pedro, salon, "16:00").json()["id"], apartamentos[0])
    assert otra_enviada.status_code == 200

    respuesta = secretaria.get("/reservas/bandeja/")

    assert respuesta.status_code == 200
    por_id = {str(item["id"]): item for item in respuesta.json()}
    assert por_id[aceptada["id"]]["estado"] == "RESERVADA"
    assert por_id[aceptada["id"]]["motivo_decision"] == "Horario aprobado."
    assert por_id[enviada["id"]]["estado"] == "RECHAZADA"
    assert por_id[enviada["id"]]["motivo_decision"] == "Falta autorización."
    assert por_id[otra_enviada.json()["id"]]["estado"] == "APARTADA"


def test_si_incumple_tres_reglas_ve_los_tres_motivos_y_se_libera_el_bloqueo(
    pedro, lucia, torres, salon, apartamentos, administracion
):
    autor = administracion[0]
    poner_aforo(torres, salon, 25)
    regla(torres, None, "ANTICIPACION_MINIMA", {"horas": 24 * 30}, autor)
    regla(torres, salon, "DIAS_QUE_NO_ABRE", {"renglones": [{"dia_semana": MANANA.weekday(), "motivo": "Limpieza"}]}, autor)
    en_tramite = tomar(pedro, salon).json()

    respuesta = enviar(pedro, en_tramite["id"], apartamentos[0], asistentes=40)

    assert respuesta.status_code == 400
    assert respuesta.json()["detail"] == "La solicitud no cumple las reglas del conjunto."
    assert sorted(respuesta.json()["motivos"]) == [
        "Esta área admite máximo 25 asistentes y la solicitud dice 40.",
        "Esta área no abre ese día: Limpieza.",
        "Esta área se solicita con al menos 720 horas de anticipación.",
    ]
    liberada = solicitud(torres, en_tramite["id"])
    assert (liberada.estado, liberada.motivo_liberacion) == ("LIBERADA", "reglas")
    assert franjas(lucia, salon)["08:00"] == "libre"


def test_sin_vivir_en_la_unidad_elegida_la_alfa_lo_impide(pedro, torres, salon, apartamentos):
    """También cierra el criterio 5 de HU-08: quien no reside no reserva a nombre de esa unidad."""
    en_tramite = tomar(pedro, salon).json()

    respuesta = enviar(pedro, en_tramite["id"], apartamentos[1])

    assert respuesta.status_code == 400
    assert respuesta.json()["motivos"] == [
        "No vives en el apartamento elegido: solo quien vive ahí puede reservar a su nombre."
    ]


def test_una_unidad_en_mora_no_pide_un_area_con_paz_y_salvo_exigido(
    monkeypatch, pedro, torres, salon, apartamentos, administracion
):
    monkeypatch.setattr(mora, "unidad_en_mora", lambda unidad: True)
    regla(torres, None, "REQUIERE_PAZ_Y_SALVO", {}, administracion[0])

    rechazada = enviar(pedro, tomar(pedro, salon).json()["id"], apartamentos[0])

    assert rechazada.json()["motivos"] == ["El apartamento no está a paz y salvo con la administración."]


def test_queda_registrado_que_reglas_se_evaluaron_y_con_que_resultado(
    pedro, torres, salon, apartamentos, administracion
):
    poner_aforo(torres, salon, 25)
    en_tramite = tomar(pedro, salon).json()

    respuesta = enviar(pedro, en_tramite["id"], apartamentos[0])

    evaluacion = respuesta.json()["evaluacion"]
    assert [(r["tipo"], r["cumple"]) for r in evaluacion] == [
        ("RESIDE", True), ("NO_EN_EL_PASADO", True), ("AREA_DISPONIBLE", True), ("AFORO", True),
    ]
    # El aforo sale del área, no de una regla: va sin id.
    assert (evaluacion[3]["id"], evaluacion[3]["parametros"]) == (None, {"maximo": 25})
    assert respuesta.json()["evaluada_en"]
    with usar_conjunto(torres.id):
        registro = Registro.objects.get(accion="reserva.enviar")
    assert registro.entidad_id == uuid.UUID(en_tramite["id"])
    assert len(registro.detalle["evaluacion"]) == 4


def test_un_envio_que_salta_la_interfaz_se_evalua_igual(pedro, torres, salon, apartamentos, administracion):
    """Criterio de HU-12: el POST directo a la API pasa por las mismas reglas."""
    poner_aforo(torres, salon, 25)

    respuesta = enviar(pedro, tomar(pedro, salon).json()["id"], apartamentos[0], asistentes=40)

    assert respuesta.status_code == 400


def test_enviar_vencida_ajena_o_dos_veces(pedro, lucia, torres, salon, apartamentos, administracion):
    vencida = tomar(pedro, salon).json()
    with usar_conjunto(torres.id):
        Solicitud.objects.filter(pk=vencida["id"]).update(bloqueo_vence_en=timezone.now() - timedelta(seconds=1))
    respuesta = enviar(pedro, vencida["id"], apartamentos[0])
    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == "Se venció el tiempo. La franja quedó libre."
    assert solicitud(torres, vencida["id"]).estado == "EXPIRADA"

    otra = tomar(pedro, salon, "12:00").json()
    assert enviar(lucia, otra["id"], apartamentos[1]).status_code == 404
    assert enviar(pedro, otra["id"], apartamentos[0]).status_code == 200
    assert enviar(pedro, otra["id"], apartamentos[0]).status_code == 409


def test_sin_motivo_o_con_cero_asistentes_no_se_envia(pedro, salon, apartamentos):
    en_tramite = tomar(pedro, salon).json()

    assert "motivo" in enviar(pedro, en_tramite["id"], apartamentos[0], motivo="").json()
    assert "asistentes" in enviar(pedro, en_tramite["id"], apartamentos[0], asistentes=0).json()
