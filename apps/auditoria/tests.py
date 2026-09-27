"""Pruebas de la auditoría de solo inserción (maestro §5.11). La piden HU-06, 07, 08, 10 y 13."""
import uuid
from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from apps.auditoria import servicios
from apps.auditoria.models import Registro, RegistroInmutable
from apps.comun.aislamiento.contexto import usar_conjunto
from apps.conjuntos.models import Conjunto
from apps.personas.models import Persona, TipoDocumento

pytestmark = pytest.mark.django_db


@pytest.fixture
def actor():
    return Persona.objects.create(
        tipo_documento=TipoDocumento.CC, numero_documento="1023456789", nombres="Laura", apellidos="Gómez"
    )


@pytest.fixture
def torres():
    conjunto = Conjunto.objects.create(nombre="Torres del Río")
    with usar_conjunto(conjunto.id):
        yield conjunto


@pytest.fixture
def registro(torres, actor):
    return servicios.registrar(
        actor, "rol.asignar", "Asignacion", uuid.uuid4(), antes=None, despues={"rol": "residente"}
    )


def test_registrar_crea_la_fila_en_el_conjunto_activo(torres, registro, actor):
    guardado = Registro.objects.get()

    assert guardado.conjunto_id == torres.id
    assert guardado.actor == actor
    assert guardado.despues == {"rol": "residente"}
    assert guardado.via_superusuario is False


def test_una_fila_guardada_no_se_modifica(registro):
    registro.accion = "otra"

    with pytest.raises(RegistroInmutable):
        registro.save()


def test_una_fila_guardada_no_se_borra(registro):
    with pytest.raises(RegistroInmutable):
        registro.delete()

    assert Registro.objects.count() == 1


def test_update_y_delete_sobre_el_queryset_tampoco(registro):
    with pytest.raises(RegistroInmutable):
        Registro.objects.filter(pk=registro.pk).update(accion="otra")
    with pytest.raises(RegistroInmutable):
        Registro.objects.all().delete()

    assert Registro.objects.get().accion == "rol.asignar"


def test_desde_otro_conjunto_no_se_ve_el_registro(registro):
    mirador = Conjunto.objects.create(nombre="Mirador")

    with usar_conjunto(mirador.id):
        assert not Registro.objects.exists()


def test_contar_solo_cuenta_la_accion_del_actor_desde_el_momento_dado(torres, actor):
    hace_dos_horas = timezone.now() - timedelta(hours=2)
    with mock.patch("django.utils.timezone.now", return_value=hace_dos_horas):
        servicios.registrar(actor, "persona.buscar", "Persona")
    servicios.registrar(actor, "persona.buscar", "Persona")
    servicios.registrar(actor, "rol.asignar", "Asignacion")

    assert servicios.contar(actor, "persona.buscar", timezone.now() - timedelta(hours=1)) == 1
