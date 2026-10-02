"""Pruebas de registro y consulta de visitantes."""

import pytest
from datetime import datetime, timedelta
from rest_framework.test import APIClient

from apps.comun.aislamiento.contexto import usar_conjunto
from apps.conjuntos.models import Conjunto
from apps.cuentas.models import TokenDeSesion, Usuario
from apps.permisos.catalogo import Rol
from apps.permisos.models import Asignacion
from apps.personas.models import Persona, TipoDocumento
from apps.unidades.models import Unidad
from apps.visitantes.models import Visitante

pytestmark = pytest.mark.django_db

CONTRASENA = "una-clave-larga-2026"


def crear_usuario(correo, conjunto, rol):
    persona = Persona.objects.create(
        tipo_documento=TipoDocumento.CC,
        numero_documento=f"1{Persona.objects.count() + 1023456789}",
        nombres="Camila",
        apellidos="Ríos",
    )
    Asignacion.objects.create(persona=persona, rol=rol, conjunto=conjunto)
    Usuario.objects.create_user(correo, CONTRASENA, persona)


def cliente_para(correo):
    cliente = APIClient()
    respuesta = cliente.post("/auth/login/", {"correo": correo, "contrasena": CONTRASENA}, format="json")
    cliente.credentials(HTTP_AUTHORIZATION=f"Token {respuesta.json()['token']}")
    TokenDeSesion.objects.filter(usuario__correo=correo).update(dos_factores_verificado=True)
    return cliente


@pytest.fixture
def datos():
    conjunto = Conjunto.objects.create(nombre="Torres del Río")
    with usar_conjunto(conjunto.id):
        unidad = Unidad.objects.create(nombre="Torre 1 – 101")
    return conjunto, unidad


def test_vigilancia_registra_y_consulta_visitantes_del_conjunto(datos):
    conjunto, unidad = datos
    crear_usuario("vigilancia@torres.com", conjunto, Rol.VIGILANCIA)
    vigilancia = cliente_para("vigilancia@torres.com")

    respuesta = vigilancia.post(
        "/visitantes/",
        {
            "nombre": "María Pérez",
            "cedula": "123456789",
            "ingresa_con_vehiculo": True,
            "placa_vehiculo": "ABC123",
            "tipo_vehiculo": "Auto",
            "apartamento_visitado": str(unidad.id),
        },
        format="json",
    )

    assert respuesta.status_code == 201
    assert respuesta.json()["apartamento_visitado"] == unidad.nombre
    hora_entrada = datetime.fromisoformat(respuesta.json()["hora_entrada"])
    assert hora_entrada.utcoffset() == timedelta(hours=-5)
    with usar_conjunto(conjunto.id):
        assert Visitante.objects.filter(cedula="123456789").exists()
    listado = vigilancia.get("/visitantes/")
    assert listado.status_code == 200
    assert listado.json()[0]["nombre"] == "María Pérez"
    assert listado.json()[0]["placa_vehiculo"] == "ABC123"
    assert listado.json()[0]["tipo_vehiculo"] == "Auto"


def test_vigilancia_registra_visitante_sin_vehiculo(datos):
    conjunto, unidad = datos
    crear_usuario("vigilancia@torres.com", conjunto, Rol.VIGILANCIA)
    vigilancia = cliente_para("vigilancia@torres.com")

    respuesta = vigilancia.post(
        "/visitantes/",
        {
            "nombre": "María Pérez",
            "cedula": "123456789",
            "ingresa_con_vehiculo": False,
            "apartamento_visitado": str(unidad.id),
        },
        format="json",
    )

    assert respuesta.status_code == 201
    assert respuesta.json()["placa_vehiculo"] == ""
    assert respuesta.json()["tipo_vehiculo"] == ""


def test_vigilancia_no_puede_registrar_vehiculo_sin_placa_y_tipo(datos):
    conjunto, unidad = datos
    crear_usuario("vigilancia@torres.com", conjunto, Rol.VIGILANCIA)
    vigilancia = cliente_para("vigilancia@torres.com")

    respuesta = vigilancia.post(
        "/visitantes/",
        {
            "nombre": "María Pérez",
            "cedula": "123456789",
            "ingresa_con_vehiculo": True,
            "apartamento_visitado": str(unidad.id),
        },
        format="json",
    )

    assert respuesta.status_code == 400
    assert "placa_vehiculo" in respuesta.json()
    assert "tipo_vehiculo" in respuesta.json()


def test_vigilancia_puede_consultar_unidades_para_el_formulario(datos):
    conjunto, unidad = datos
    crear_usuario("vigilancia@torres.com", conjunto, Rol.VIGILANCIA)
    vigilancia = cliente_para("vigilancia@torres.com")

    respuesta = vigilancia.get("/unidades/")

    assert respuesta.status_code == 200
    assert respuesta.json()[0]["nombre"] == unidad.nombre


def test_no_se_puede_registrar_una_visita_a_unidad_de_otro_conjunto(datos):
    conjunto, _ = datos
    otro_conjunto = Conjunto.objects.create(nombre="Mirador")
    with usar_conjunto(otro_conjunto.id):
        unidad_ajena = Unidad.objects.create(nombre="Torre 2 – 202")
    crear_usuario("vigilancia@torres.com", conjunto, Rol.VIGILANCIA)
    vigilancia = cliente_para("vigilancia@torres.com")

    respuesta = vigilancia.post(
        "/visitantes/",
        {
            "nombre": "María Pérez",
            "cedula": "123456789",
            "apartamento_visitado": str(unidad_ajena.id),
        },
        format="json",
    )

    assert respuesta.status_code == 404
    with usar_conjunto(conjunto.id):
        assert Visitante.objects.count() == 0


def test_personas_sin_permiso_no_pueden_consultar_visitantes(datos):
    conjunto, _ = datos
    crear_usuario("residente@torres.com", conjunto, Rol.RESIDENTE)
    residente = cliente_para("residente@torres.com")

    respuesta = residente.get("/visitantes/")

    assert respuesta.status_code == 403
