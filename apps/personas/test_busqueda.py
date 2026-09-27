"""Pruebas de HU-07: buscar a una persona por documento exacto y vincularla al conjunto activo."""
from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.auditoria import servicios as auditoria
from apps.auditoria.models import Registro
from apps.comun.aislamiento.contexto import usar_conjunto
from apps.conjuntos.models import Conjunto
from apps.cuentas.models import TokenDeSesion, Usuario
from apps.permisos.catalogo import PERMISOS_POR_ROL, Rol
from apps.permisos.models import Asignacion
from apps.permisos.servicios import permisos_efectivos
from apps.personas.models import Persona, TipoDocumento

pytestmark = pytest.mark.django_db

CONTRASENA = "una-clave-larga-2026"


def crear_persona(numero, nombres, *roles, correo=None, telefono=""):
    persona = Persona.objects.create(
        tipo_documento=TipoDocumento.CC, numero_documento=numero, nombres=nombres, apellidos="Gómez", telefono=telefono
    )
    for rol, conjunto in roles:
        Asignacion.objects.create(persona=persona, rol=rol, conjunto=conjunto)
    if correo:
        Usuario.objects.create_user(correo, CONTRASENA, persona)
    return persona


def cliente_para(correo):
    """Sesión con el segundo factor dado por verificado: su flujo se prueba en cuentas."""
    cliente = APIClient()
    respuesta = cliente.post("/auth/login/", {"correo": correo, "contrasena": CONTRASENA}, format="json")
    cliente.credentials(HTTP_AUTHORIZATION=f"Token {respuesta.json()['token']}")
    TokenDeSesion.objects.filter(usuario__correo=correo).update(dos_factores_verificado=True)
    return cliente


@pytest.fixture
def torres():
    return Conjunto.objects.create(nombre="Torres del Río")


@pytest.fixture
def mirador():
    return Conjunto.objects.create(nombre="Mirador")


@pytest.fixture
def andres(torres):
    return crear_persona("80000001", "Andrés", (Rol.ADMINISTRACION, torres), correo="admin@torres.com")


@pytest.fixture
def admin(andres):
    return cliente_para("admin@torres.com")


@pytest.fixture
def vigilante(mirador):
    """Vive en Mirador; lo van a vincular en Torres. Tiene teléfono y cuenta."""
    return crear_persona(
        "1023456789", "Carlos", (Rol.ADMINISTRACION, mirador), correo="carlos@correo.com", telefono="3001234567"
    )


def buscar(cliente, numero, tipo="CC"):
    return cliente.post("/personas/buscar/", {"tipo_documento": tipo, "numero_documento": numero}, format="json")


def vincular(cliente, persona, rol="residente"):
    return cliente.post("/personas/vincular/", {"persona": str(persona.id), "rol": rol}, format="json")


def registros_de_busqueda(conjunto):
    with usar_conjunto(conjunto.id):
        return list(Registro.objects.filter(accion="persona.buscar").order_by("creado_en"))


# Criterios de aceptación


def test_documento_existente_se_vincula_sin_crear_otra_persona(admin, torres, vigilante):
    personas_antes = Persona.objects.count()

    encontrada = buscar(admin, "1023456789").json()
    respuesta = vincular(admin, vigilante, "vigilancia")

    assert encontrada["encontrada"] is True
    assert encontrada["persona"]["id"] == str(vigilante.id)
    assert respuesta.status_code == 201
    assert respuesta.json()["roles_en_el_conjunto"] == ["Vigilancia"]
    assert Persona.objects.count() == personas_antes
    assert Asignacion.objects.vigentes().filter(persona=vigilante, conjunto=torres, rol=Rol.VIGILANCIA).exists()


def test_documento_inexistente_no_encuentra_a_nadie(admin):
    assert buscar(admin, "99999999").json() == {"encontrada": False}


def test_cada_busqueda_queda_en_la_auditoria_con_quien_y_que_documento(admin, torres, andres, vigilante):
    buscar(admin, "1.023.456.789")
    buscar(admin, "99999999")

    registros = registros_de_busqueda(torres)
    assert [(r.actor_id, r.detalle, r.entidad_id) for r in registros] == [
        (andres.id, {"tipo_documento": "CC", "numero_documento": "1023456789"}, vigilante.id),
        (andres.id, {"tipo_documento": "CC", "numero_documento": "99999999"}, None),
    ]


def test_pasar_el_limite_de_busquedas_se_rechaza(admin, torres, andres):
    with usar_conjunto(torres.id):
        with mock.patch("django.utils.timezone.now", return_value=timezone.now() - timedelta(hours=2)):
            auditoria.registrar(andres, "persona.buscar", "Persona")
        for _ in range(19):
            auditoria.registrar(andres, "persona.buscar", "Persona")

    # La de hace dos horas no cuenta: esta es la número 20 de la última hora.
    assert buscar(admin, "99999999").status_code == 200
    respuesta = buscar(admin, "99999999")

    assert respuesta.status_code == 429
    assert respuesta.json()["detail"] == "Hiciste demasiadas búsquedas. Espera un rato e intenta de nuevo."
    assert len(registros_de_busqueda(torres)) == 21


def test_vinculada_a_dos_conjuntos_sus_roles_del_otro_no_dan_permisos(admin, torres, mirador, vigilante):
    vincular(admin, vigilante, "residente")

    assert permisos_efectivos(vigilante, torres.id) == PERMISOS_POR_ROL[Rol.RESIDENTE]
    assert permisos_efectivos(vigilante, mirador.id) == PERMISOS_POR_ROL[Rol.ADMINISTRACION]


# Reglas de la búsqueda


def test_con_puntos_y_espacios_encuentra_igual_y_un_numero_parcial_no(admin, vigilante):
    assert buscar(admin, " 1.023 456 789 ").json()["encontrada"] is True
    assert buscar(admin, "1023456").json()["encontrada"] is False
    assert buscar(admin, "1023456789", tipo="TI").json()["encontrada"] is False


def test_la_respuesta_no_trae_telefono_correo_ni_datos_de_otros_conjuntos(admin, vigilante):
    respuesta = buscar(admin, "1023456789")

    texto = respuesta.content.decode()
    assert "3001234567" not in texto and "carlos@correo.com" not in texto
    assert "Mirador" not in texto
    assert respuesta.json()["persona"] == {
        "id": str(vigilante.id), "nombre": "Carlos Gómez", "tiene_cuenta": True, "roles_en_el_conjunto": []
    }


def test_vincular_un_rol_ya_vigente_responde_409(admin, torres, vigilante):
    vincular(admin, vigilante, "residente")

    assert vincular(admin, vigilante, "residente").status_code == 409


def test_sin_permiso_no_se_busca_ni_se_vincula(torres, vigilante):
    crear_persona("80000002", "Pedro", (Rol.RESIDENTE, torres), correo="vecino@torres.com")
    residente = cliente_para("vecino@torres.com")

    assert buscar(residente, "1023456789").status_code == 403
    assert vincular(residente, vigilante).status_code == 403
    assert registros_de_busqueda(torres) == []
