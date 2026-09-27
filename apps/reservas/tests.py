"""Pruebas de HU-11: franjas y bloqueo exclusivo de 3 minutos.

La concurrencia (N residentes sobre la misma franja) va en `tests/concurrencia/test_bloqueo_de_franjas.py`.
"""
from datetime import datetime, time, timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.areas.models import Area, Clasificacion
from apps.comun.aislamiento.contexto import usar_conjunto
from apps.conjuntos.models import Conjunto
from apps.cuentas.models import TokenDeSesion, Usuario
from apps.permisos.catalogo import Rol
from apps.permisos.models import Asignacion
from apps.personas.models import Persona, TipoDocumento
from apps.reglas.models import Regla
from apps.reservas.models import Solicitud
from apps.reservas.servicios import avisos
from apps.unidades.models import TipoVinculo, Unidad, VinculoUnidad

pytestmark = pytest.mark.django_db

CONTRASENA = "una-clave-larga-2026"
MANANA = timezone.localdate() + timedelta(days=1)


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
        "clasificacion": Clasificacion.COMUN, "hora_apertura": time(8), "hora_cierre": time(22),
        "duracion_franja_minutos": 240, **extra,
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
    madrugada = crear_area(torres, "Cancha", hora_apertura=time(0), hora_cierre=time(23), duracion_franja_minutos=60)
    hoy = timezone.localdate()

    assert tomar(pedro, madrugada, "00:00", hoy).status_code == 400
    assert franjas(pedro, madrugada, hoy)["00:00"] == "pasada"
    assert tomar(pedro, madrugada, "08:30").status_code == 400  # no es el inicio de ninguna franja


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
        Regla.objects.create(area=salon, tipo="ANTICIPACION_MAXIMA", parametros={"dias": 30}, creada_por=ana)
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
