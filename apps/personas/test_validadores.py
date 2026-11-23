"""Formato del documento, los nombres, la cédula y la placa al crear (apps/personas/validadores.py)."""
import pytest
from rest_framework import serializers

from apps.cuentas.serializers import CrearSuperusuarioSerializer
from apps.personas.models import TipoDocumento
from apps.personas.validadores import validar_documento
from apps.visitantes.serializers import RegistrarVisitanteSerializer

pytestmark = pytest.mark.django_db

SUPERUSUARIO = {
    "tipo_documento": "CC",
    "numero_documento": "1023456789",
    "nombres": "María José",
    "apellidos": "Núñez-O'Neil",
    "correo": "maria@correo.com",
    "contrasena": "Clave-segura-2026",
}


def errores(**cambios):
    serializer = CrearSuperusuarioSerializer(data={**SUPERUSUARIO, **cambios})
    serializer.is_valid()
    return serializer.errors


def test_datos_validos_pasan():
    assert errores() == {}


@pytest.mark.parametrize("numero", ["10234AB789", "1023-456", "abc12345"])
def test_la_cedula_no_acepta_letras_ni_simbolos(numero):
    assert errores(numero_documento=numero)["numero_documento"] == [
        "En este campo solo se aceptan números, sin puntos ni espacios."
    ]


@pytest.mark.parametrize("numero", ["1234", "123456789012"])
def test_el_documento_tiene_entre_5_y_11_caracteres(numero):
    assert errores(numero_documento=numero)["numero_documento"] == [
        "El documento debe tener entre 5 y 11 caracteres."
    ]


def test_los_puntos_y_espacios_se_quitan_antes_de_validar():
    assert validar_documento(TipoDocumento.CC, "1.023.456 789") == "1023456789"


def test_el_pasaporte_acepta_letras_pero_no_simbolos():
    assert errores(tipo_documento="PAS", numero_documento="ab123456") == {}
    with pytest.raises(serializers.ValidationError):
        validar_documento(TipoDocumento.PAS, "AB-123456")


@pytest.mark.parametrize("campo", ["nombres", "apellidos"])
def test_nombres_y_apellidos_solo_aceptan_letras(campo):
    assert errores(**{campo: "Ana2"})[campo] == ["En este campo solo se aceptan letras y espacios."]


def test_el_visitante_valida_cedula_nombre_y_placa():
    serializer = RegistrarVisitanteSerializer(
        data={
            "nombre": "Pedro 3",
            "cedula": "12345abc",
            "ingresa_con_vehiculo": True,
            "placa_vehiculo": "ABC-123",
            "tipo_vehiculo": "Auto",
            "apartamento_visitado": "8f5c6a0e-0000-4000-8000-000000000000",
        }
    )
    assert not serializer.is_valid()
    assert set(serializer.errors) == {"nombre", "cedula", "placa_vehiculo"}
