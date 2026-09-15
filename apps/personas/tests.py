"""Pruebas de HU-04: persona global única por documento."""
import uuid

import pytest
from django.db import IntegrityError, transaction

from apps.personas.models import Persona, TipoDocumento

pytestmark = pytest.mark.django_db


def crear_persona(tipo=TipoDocumento.CC, numero="1023456789"):
    return Persona.objects.create(
        tipo_documento=tipo,
        numero_documento=numero,
        nombres="Laura",
        apellidos="Gómez",
    )


def test_documento_existente_no_crea_segunda_persona():
    crear_persona(numero="1023456789")

    with pytest.raises(IntegrityError, match="persona_documento_unico"), transaction.atomic():
        crear_persona(numero="1023456789")

    assert Persona.objects.count() == 1


def test_mismo_documento_escrito_distinto_tampoco_crea_segunda_persona():
    crear_persona(numero="1023456789")

    with pytest.raises(IntegrityError, match="persona_documento_unico"), transaction.atomic():
        crear_persona(numero="1.023.456.789")

    assert Persona.objects.count() == 1


def test_mismo_numero_con_distinto_tipo_es_otra_persona():
    cedula = crear_persona(tipo=TipoDocumento.CC, numero="1023456789")
    tarjeta = crear_persona(tipo=TipoDocumento.TI, numero="1023456789")

    assert cedula.pk != tarjeta.pk
    assert Persona.objects.count() == 2


@pytest.mark.parametrize(
    "tipo, escrito, guardado",
    [
        (TipoDocumento.CC, "1.023.456.789", "1023456789"),
        (TipoDocumento.CC, " 1023 456 789 ", "1023456789"),
        (TipoDocumento.CC, "0001023456789", "1023456789"),
        (TipoDocumento.PAS, "ab123456", "AB123456"),
    ],
)
def test_numero_queda_normalizado_al_guardar(tipo, escrito, guardado):
    persona = crear_persona(tipo=tipo, numero=escrito)
    persona.refresh_from_db()

    assert persona.numero_documento == guardado


def test_persona_se_identifica_por_uuid():
    persona = crear_persona()

    assert isinstance(persona.pk, uuid.UUID)


def test_base_rechaza_tipo_de_documento_fuera_del_catalogo():
    with pytest.raises(IntegrityError, match="persona_tipo_documento_valido"), transaction.atomic():
        crear_persona(tipo="PA")


def test_base_rechaza_numero_sin_normalizar_aunque_no_pase_por_save():
    persona = crear_persona()

    with pytest.raises(IntegrityError, match="persona_documento_normalizado"), transaction.atomic():
        Persona.objects.filter(pk=persona.pk).update(numero_documento="1.023.456.789")
