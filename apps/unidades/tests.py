"""Pruebas de las unidades y del enrutamiento por vínculos (maestro §5.5).

Es lo mínimo que necesita HU-25. La pantalla de unidades y vínculos es de HU-08.
"""
from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.comun.aislamiento.contexto import usar_conjunto
from apps.conjuntos.models import Conjunto
from apps.personas.models import Persona, TipoDocumento
from apps.unidades.models import TipoVinculo, Unidad, VinculoUnidad
from apps.unidades.servicios import Hecho, destinatarios, unidades_de

pytestmark = pytest.mark.django_db


def crear_persona(nombres):
    return Persona.objects.create(
        tipo_documento=TipoDocumento.CC,
        numero_documento=str(Persona.objects.count() + 1023456789),
        nombres=nombres,
        apellidos="Gómez",
    )


@pytest.fixture
def torres():
    conjunto = Conjunto.objects.create(nombre="Torres del Río")
    with usar_conjunto(conjunto.id):
        yield conjunto


@pytest.fixture
def apto_402(torres):
    return Unidad.objects.create(nombre="Torre 3 – 402")


@pytest.fixture
def propietaria_que_arrienda(apto_402):
    """Dueña que no vive ahí, y un arrendatario que sí: dos vínculos sobre la misma unidad."""
    duena = crear_persona("Marta")
    inquilino = crear_persona("Pedro")
    VinculoUnidad.objects.create(persona=duena, unidad=apto_402, tipo=TipoVinculo.PROPIETARIO, reside=False)
    VinculoUnidad.objects.create(persona=inquilino, unidad=apto_402, tipo=TipoVinculo.ARRENDATARIO, reside=True)
    return duena, inquilino


def nombres(personas):
    return sorted(persona.nombres for persona in personas)


@pytest.mark.parametrize(
    ("hecho", "esperados"),
    [
        (Hecho.ANUNCIO_A_VIVIENDA, ["Marta", "Pedro"]),
        (Hecho.OPERATIVO, ["Pedro"]),
        (Hecho.ASAMBLEA, ["Marta"]),
        (Hecho.INFRACCION, ["Marta", "Pedro"]),
        (Hecho.MORA, ["Marta"]),
    ],
)
def test_cada_hecho_llega_a_quien_corresponde_segun_el_vinculo(apto_402, propietaria_que_arrienda, hecho, esperados):
    assert nombres(destinatarios(apto_402, hecho)) == esperados


def test_un_vinculo_cerrado_ya_no_recibe_nada_pero_se_conserva(apto_402, propietaria_que_arrienda):
    _, inquilino = propietaria_que_arrienda
    VinculoUnidad.objects.filter(persona=inquilino).update(vigencia_hasta=timezone.localdate())

    assert nombres(destinatarios(apto_402, Hecho.ANUNCIO_A_VIVIENDA)) == ["Marta"]
    assert VinculoUnidad.objects.filter(persona=inquilino).exists()


def test_un_vinculo_que_aun_no_empieza_no_recibe_nada(apto_402):
    futura = crear_persona("Ana")
    manana = timezone.localdate() + timedelta(days=1)
    VinculoUnidad.objects.create(
        persona=futura, unidad=apto_402, tipo=TipoVinculo.ARRENDATARIO, reside=True, vigencia_desde=manana
    )

    assert not destinatarios(apto_402, Hecho.ANUNCIO_A_VIVIENDA).exists()


def test_no_hay_dos_vinculos_vigentes_iguales_sobre_la_misma_unidad(apto_402, propietaria_que_arrienda):
    duena, _ = propietaria_que_arrienda

    with pytest.raises(IntegrityError), transaction.atomic():
        VinculoUnidad.objects.create(persona=duena, unidad=apto_402, tipo=TipoVinculo.PROPIETARIO, reside=True)


def test_unidades_de_una_persona_son_solo_las_de_sus_vinculos_vigentes(apto_402, propietaria_que_arrienda):
    Unidad.objects.create(nombre="Torre 3 – 403")
    duena, _ = propietaria_que_arrienda

    assert [unidad.nombre for unidad in unidades_de(duena)] == ["Torre 3 – 402"]


def test_la_base_no_deja_que_un_vinculo_apunte_a_una_unidad_de_otro_conjunto(torres):
    mirador = Conjunto.objects.create(nombre="Mirador")
    with usar_conjunto(mirador.id):
        ajena = Unidad.objects.create(nombre="Casa 1")
    persona = crear_persona("Laura")

    with pytest.raises(IntegrityError), transaction.atomic():
        # Se salta save() a propósito: la última barrera es la FK compuesta en la base.
        VinculoUnidad.objects.bulk_create(
            [VinculoUnidad(conjunto=torres, persona=persona, unidad=ajena, tipo=TipoVinculo.PROPIETARIO, reside=True)]
        )
