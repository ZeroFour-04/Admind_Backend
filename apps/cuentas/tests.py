"""Pruebas de HU-01: inicio y cierre de sesión con token."""
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.cuentas.models import TokenDeSesion, Usuario
from apps.personas.models import Persona, TipoDocumento

pytestmark = pytest.mark.django_db

CONTRASENA = "una-clave-larga-2026"


@pytest.fixture
def cliente():
    return APIClient()


@pytest.fixture
def usuario():
    persona = Persona.objects.create(
        tipo_documento=TipoDocumento.CC,
        numero_documento="1023456789",
        nombres="Laura",
        apellidos="Gómez",
    )
    return Usuario.objects.create_user("laura@correo.com", CONTRASENA, persona)


def iniciar_sesion(cliente, correo, contrasena):
    return cliente.post("/auth/login/", {"correo": correo, "contrasena": contrasena}, format="json")


def cerrar_sesion(cliente, token=None):
    if token:
        cliente.credentials(HTTP_AUTHORIZATION=f"Token {token}")
    return cliente.post("/auth/logout/")


# Inicio de sesión


def test_credenciales_validas_entregan_un_token(cliente, usuario):
    respuesta = iniciar_sesion(cliente, "laura@correo.com", CONTRASENA)

    assert respuesta.status_code == 200
    assert respuesta.json()["token"]
    assert TokenDeSesion.objects.filter(usuario=usuario).count() == 1


def test_correo_se_acepta_con_mayusculas_y_espacios(cliente, usuario):
    respuesta = iniciar_sesion(cliente, "  Laura@Correo.com ", CONTRASENA)

    assert respuesta.status_code == 200


def test_la_base_guarda_la_huella_y_no_el_token(cliente, usuario):
    token = iniciar_sesion(cliente, "laura@correo.com", CONTRASENA).json()["token"]

    assert not TokenDeSesion.objects.filter(huella=token).exists()


def test_errores_de_ingreso_no_revelan_si_el_correo_existe(cliente, usuario):
    contrasena_mala = iniciar_sesion(cliente, "laura@correo.com", "otra-clave")
    correo_inexistente = iniciar_sesion(cliente, "nadie@correo.com", CONTRASENA)

    assert contrasena_mala.status_code == correo_inexistente.status_code == 401
    assert contrasena_mala.json() == correo_inexistente.json()


def test_usuario_desactivado_no_puede_entrar(cliente, usuario):
    usuario.is_active = False
    usuario.save()

    respuesta = iniciar_sesion(cliente, "laura@correo.com", CONTRASENA)

    assert respuesta.status_code == 401
    assert not TokenDeSesion.objects.exists()


def test_persona_desactivada_no_puede_entrar(cliente, usuario):
    Persona.objects.filter(pk=usuario.persona_id).update(activo=False)

    respuesta = iniciar_sesion(cliente, "laura@correo.com", CONTRASENA)

    assert respuesta.status_code == 401


# Uso del token


def test_sin_token_la_api_responde_401(cliente, usuario):
    assert cerrar_sesion(cliente).status_code == 401


def test_token_inventado_responde_401(cliente, usuario):
    assert cerrar_sesion(cliente, "no-es-un-token").status_code == 401


def test_token_vencido_exige_iniciar_sesion_de_nuevo(cliente, usuario):
    token = iniciar_sesion(cliente, "laura@correo.com", CONTRASENA).json()["token"]
    TokenDeSesion.objects.update(vence_en=timezone.now() - timedelta(minutes=1))

    assert cerrar_sesion(cliente, token).status_code == 401


def test_desactivar_al_usuario_invalida_su_token_de_inmediato(cliente, usuario):
    token = iniciar_sesion(cliente, "laura@correo.com", CONTRASENA).json()["token"]
    usuario.is_active = False
    usuario.save()

    assert cerrar_sesion(cliente, token).status_code == 401


# Cierre de sesión


def test_cerrar_sesion_invalida_el_token_de_inmediato(cliente, usuario):
    token = iniciar_sesion(cliente, "laura@correo.com", CONTRASENA).json()["token"]

    assert cerrar_sesion(cliente, token).status_code == 204
    assert cerrar_sesion(cliente, token).status_code == 401
    assert not TokenDeSesion.objects.exists()
