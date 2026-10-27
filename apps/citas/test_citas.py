"""Pruebas de API y persistencia de la configuración semanal de citas."""

import pytest
from datetime import timedelta
from rest_framework.test import APIClient
from django.utils import timezone

from apps.auditoria.models import Registro
from apps.citas.models import Cita, EstadoCita, HorarioDeAtencion
from apps.comun.aislamiento.contexto import usar_conjunto
from apps.conjuntos.models import Conjunto
from apps.cuentas.models import TokenDeSesion, Usuario
from apps.permisos.catalogo import Rol
from apps.permisos.models import Asignacion
from apps.personas.models import Persona, TipoDocumento

pytestmark = pytest.mark.django_db

CONTRASENA = "una-clave-larga-2026"


def crear_cliente(conjunto, correo, rol):
    persona = Persona.objects.create(
        tipo_documento=TipoDocumento.CC,
        numero_documento=str(Persona.objects.count() + 1023456789),
        nombres="Laura",
        apellidos="Gómez",
    )
    with usar_conjunto(conjunto.id):
        Asignacion.objects.create(persona=persona, rol=rol, conjunto=conjunto)
    Usuario.objects.create_user(correo, CONTRASENA, persona)
    cliente = APIClient()
    sesion = cliente.post("/auth/login/", {"correo": correo, "contrasena": CONTRASENA}, format="json")
    cliente.credentials(HTTP_AUTHORIZATION=f"Token {sesion.json()['token']}")
    TokenDeSesion.objects.filter(usuario__correo=correo).update(dos_factores_verificado=True)
    return cliente


def dias_iniciales():
    return [
        {
            "dia": dia,
            "activo": dia < 5,
            "hora_inicio": "08:00" if dia < 5 else None,
            "hora_fin": "17:00" if dia < 5 else None,
            "descanso_inicio": "12:00" if dia < 5 else None,
            "descanso_fin": "14:00" if dia < 5 else None,
        }
        for dia in range(7)
    ]


def test_administracion_configura_horario_semanal_con_descanso():
    conjunto = Conjunto.objects.create(nombre="Torres del Río")
    cliente = crear_cliente(conjunto, "admin@torres.com", Rol.ADMINISTRACION)

    inicial = cliente.get("/citas/horario/")
    guardado = cliente.put("/citas/horario/", {"dias": dias_iniciales()}, format="json")

    assert inicial.status_code == 200 and len(inicial.json()["dias"]) == 7
    assert guardado.status_code == 200
    assert guardado.json()["dias"][0]["descanso_inicio"] == "12:00"
    with usar_conjunto(conjunto.id):
        horario = HorarioDeAtencion.objects.get()
        registro = Registro.objects.get(accion="cita.horario.editar")
    assert horario.actualizado_por == Persona.objects.get(nombres="Laura")
    assert registro.despues == guardado.json()["dias"]


def test_el_horario_rechaza_descanso_fuera_de_la_atencion():
    conjunto = Conjunto.objects.create(nombre="Torres del Río")
    cliente = crear_cliente(conjunto, "admin@torres.com", Rol.ADMINISTRACION)
    dias = dias_iniciales()
    dias[0]["descanso_inicio"] = "16:00"
    dias[0]["descanso_fin"] = "18:00"

    respuesta = cliente.put("/citas/horario/", {"dias": dias}, format="json")

    assert respuesta.status_code == 400
    with usar_conjunto(conjunto.id):
        assert not HorarioDeAtencion.objects.exists()


def test_residente_puede_consultar_el_horario_sin_poder_editarlo():
    conjunto = Conjunto.objects.create(nombre="Torres del Río")
    cliente = crear_cliente(conjunto, "vecino@torres.com", Rol.RESIDENTE)

    assert cliente.get("/citas/horario/").status_code == 200
    assert cliente.put("/citas/horario/", {"dias": dias_iniciales()}, format="json").status_code == 403


def proximo_dia_habil():
    fecha = timezone.localdate() + timedelta(days=1)
    while fecha.weekday() >= 5:
        fecha += timedelta(days=1)
    return fecha + timedelta(days=7)


def test_residente_consulta_horario_y_franjas_de_dos_horas_sin_ofrecer_descanso():
    conjunto = Conjunto.objects.create(nombre="Torres del Río")
    admin = crear_cliente(conjunto, "admin@torres.com", Rol.ADMINISTRACION)
    residente = crear_cliente(conjunto, "vecino@torres.com", Rol.RESIDENTE)
    assert admin.put("/citas/horario/", {"dias": dias_iniciales()}, format="json").status_code == 200
    fecha = proximo_dia_habil()

    respuesta = residente.get(f"/citas/agenda/?fecha={fecha.isoformat()}")

    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert len(datos["horario"]["dias"]) == 7
    assert [(franja["hora_inicio"][:5], franja["hora_fin"][:5]) for franja in datos["franjas"]] == [
        ("08:00", "10:00"),
        ("10:00", "12:00"),
        ("14:00", "16:00"),
    ]
    assert all(franja["estado"] == "libre" for franja in datos["franjas"])


def test_reserva_es_exclusiva_y_el_residente_solo_puede_tener_una_cita_futura():
    conjunto = Conjunto.objects.create(nombre="Torres del Río")
    admin = crear_cliente(conjunto, "admin@torres.com", Rol.ADMINISTRACION)
    residente = crear_cliente(conjunto, "vecino@torres.com", Rol.RESIDENTE)
    otro_residente = crear_cliente(conjunto, "vecina@torres.com", Rol.RESIDENTE)
    assert admin.put("/citas/horario/", {"dias": dias_iniciales()}, format="json").status_code == 200
    fecha = proximo_dia_habil()
    datos = {"fecha": fecha.isoformat(), "hora_inicio": "08:00"}

    agendada = residente.post("/citas/agenda/", datos, format="json")
    repetida = otro_residente.post("/citas/agenda/", datos, format="json")
    segunda = residente.post(
        "/citas/agenda/",
        {"fecha": fecha.isoformat(), "hora_inicio": "10:00"},
        format="json",
    )

    assert agendada.status_code == 201
    assert agendada.json()["hora_fin"][:5] == "10:00"
    assert repetida.status_code == 409
    assert segunda.status_code == 409
    with usar_conjunto(conjunto.id):
        assert Cita.objects.filter(estado=EstadoCita.AGENDADA).count() == 1


def test_una_cita_vencida_pasa_a_atendida_y_no_bloquea_una_nueva():
    conjunto = Conjunto.objects.create(nombre="Torres del Río")
    admin = crear_cliente(conjunto, "admin@torres.com", Rol.ADMINISTRACION)
    residente = crear_cliente(conjunto, "vecino@torres.com", Rol.RESIDENTE)
    assert admin.put("/citas/horario/", {"dias": dias_iniciales()}, format="json").status_code == 200
    fecha = proximo_dia_habil()
    with usar_conjunto(conjunto.id):
        anterior = Cita.objects.create(
            conjunto=conjunto,
            persona=Usuario.objects.get(correo="vecino@torres.com").persona,
            fecha=timezone.localdate() - timedelta(days=2),
            hora_inicio="08:00",
            hora_fin="10:00",
            vence_en=timezone.now() - timedelta(days=1),
        )

    nueva = residente.post(
        "/citas/agenda/",
        {"fecha": fecha.isoformat(), "hora_inicio": "08:00"},
        format="json",
    )

    assert nueva.status_code == 201
    with usar_conjunto(conjunto.id):
        anterior.refresh_from_db()
        assert anterior.estado == EstadoCita.ATENDIDA


def test_no_se_puede_agendar_durante_el_descanso_o_fuera_del_horario():
    conjunto = Conjunto.objects.create(nombre="Torres del Río")
    admin = crear_cliente(conjunto, "admin@torres.com", Rol.ADMINISTRACION)
    residente = crear_cliente(conjunto, "vecino@torres.com", Rol.RESIDENTE)
    assert admin.put("/citas/horario/", {"dias": dias_iniciales()}, format="json").status_code == 200
    fecha = proximo_dia_habil()

    durante_descanso = residente.post(
        "/citas/agenda/",
        {"fecha": fecha.isoformat(), "hora_inicio": "12:00"},
        format="json",
    )
    fuera_horario = residente.post(
        "/citas/agenda/",
        {"fecha": fecha.isoformat(), "hora_inicio": "16:00"},
        format="json",
    )

    assert durante_descanso.status_code == 400
    assert fuera_horario.status_code == 400


def test_solo_residentes_pueden_agendar():
    conjunto = Conjunto.objects.create(nombre="Torres del Río")
    admin = crear_cliente(conjunto, "admin@torres.com", Rol.ADMINISTRACION)

    respuesta = admin.post(
        "/citas/agenda/",
        {"fecha": proximo_dia_habil().isoformat(), "hora_inicio": "08:00"},
        format="json",
    )

    assert respuesta.status_code == 403


def test_administracion_ve_sus_citas_y_residente_no_puede_ver_la_bandeja():
    conjunto = Conjunto.objects.create(nombre="Torres del Río")
    admin = crear_cliente(conjunto, "admin@torres.com", Rol.ADMINISTRACION)
    residente = crear_cliente(conjunto, "vecino@torres.com", Rol.RESIDENTE)
    assert admin.put("/citas/horario/", {"dias": dias_iniciales()}, format="json").status_code == 200
    fecha = proximo_dia_habil()
    assert residente.post(
        "/citas/agenda/",
        {"fecha": fecha.isoformat(), "hora_inicio": "08:00"},
        format="json",
    ).status_code == 201

    bandeja = admin.get("/citas/bandeja/")

    assert bandeja.status_code == 200
    assert bandeja.json()[0]["residente"] == "Laura Gómez"
    assert residente.get("/citas/bandeja/").status_code == 403
