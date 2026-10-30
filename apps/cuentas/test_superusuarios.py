"""Pruebas del alta de Superusuarios desde la plataforma (HU-06)."""
import pytest
from rest_framework.test import APIClient

from apps.conjuntos.models import Conjunto
from apps.cuentas.models import Usuario
from apps.cuentas.tests import (
    CONTRASENA,
    asignar,
    cliente,
    contador_de_enlaces_en_cero,
    entrar,
    iniciar_sesion,
    usuario,
)
from apps.permisos.catalogo import Rol
from apps.permisos.models import Asignacion

pytestmark = pytest.mark.django_db


def datos_superusuario(**extra):
    datos = {
        "tipo_documento": "CC",
        "numero_documento": "9876543210",
        "nombres": "Carlos",
        "apellidos": "Ruiz",
        "correo": "carlos@correo.com",
        "contrasena": CONTRASENA,
    }
    datos.update(extra)
    return datos


def test_superusuario_crea_otro_superusuario(cliente, usuario):
    asignar(usuario, Rol.SUPERUSUARIO, conjunto=None)
    entrar(cliente)

    respuesta = cliente.post("/auth/superusuarios/", datos_superusuario(), format="json")

    assert respuesta.status_code == 201
    assert respuesta.json()["correo"] == "carlos@correo.com"
    nuevo_id = respuesta.json()["id"]

    asignacion = Asignacion.objects.get(persona__usuario__id=nuevo_id)
    assert asignacion.rol == Rol.SUPERUSUARIO
    assert asignacion.conjunto is None


def test_administrador_con_conjunto_activo_recibe_403(cliente, usuario):
    torres = Conjunto.objects.create(nombre="Torres del Río")
    asignar(usuario, Rol.ADMINISTRACION, torres)
    entrar(cliente)

    respuesta = cliente.post("/auth/superusuarios/", datos_superusuario(), format="json")

    assert respuesta.status_code == 403
    assert not Usuario.objects.filter(correo="carlos@correo.com").exists()


def test_documento_repetido_responde_400(cliente, usuario):
    asignar(usuario, Rol.SUPERUSUARIO, conjunto=None)
    entrar(cliente)

    respuesta = cliente.post(
        "/auth/superusuarios/",
        datos_superusuario(numero_documento="1023456789", correo="otro@correo.com"),
        format="json",
    )

    assert respuesta.status_code == 400
    assert "numero_documento" in respuesta.json()


def test_ignora_campo_rol_en_peticion_y_asigna_superusuario(cliente, usuario):
    asignar(usuario, Rol.SUPERUSUARIO, conjunto=None)
    entrar(cliente)

    respuesta = cliente.post(
        "/auth/superusuarios/",
        datos_superusuario(rol="residente"),
        format="json",
    )

    assert respuesta.status_code == 201
    asignacion = Asignacion.objects.get(persona__usuario__correo="carlos@correo.com")
    assert asignacion.rol == Rol.SUPERUSUARIO
    assert asignacion.conjunto is None


def test_nuevo_superusuario_inicia_sesion_y_exige_dos_factores(cliente, usuario):
    asignar(usuario, Rol.SUPERUSUARIO, conjunto=None)
    entrar(cliente)

    cliente.post("/auth/superusuarios/", datos_superusuario(), format="json")

    cliente.credentials()
    login = iniciar_sesion(cliente, "carlos@correo.com", CONTRASENA)

    assert login.status_code == 200
    assert login.json()["dos_factores"]["requerido"] is True
    assert login.json()["dos_factores"]["configurado"] is False
