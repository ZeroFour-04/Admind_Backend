"""HU-05 en la capa de datos: el filtro por conjunto activo y la FK compuesta."""
import pytest
from django.db import IntegrityError, transaction

from apps.comun.aislamiento.contexto import EscrituraEnOtroConjunto, SinConjuntoActivo, usar_conjunto
from apps.conjuntos.models import Conjunto
from tests.aislamiento.models import Area, Reserva

pytestmark = pytest.mark.django_db


@pytest.fixture
def torres():
    return Conjunto.objects.create(nombre="Torres del Río")


@pytest.fixture
def mirador():
    return Conjunto.objects.create(nombre="Mirador")


def crear_area(conjunto, nombre):
    with usar_conjunto(conjunto.id):
        return Area.objects.create(nombre=nombre)


def test_listado_solo_trae_filas_del_conjunto_activo(torres, mirador):
    crear_area(torres, "Salón comunal")
    crear_area(mirador, "Piscina")

    with usar_conjunto(torres.id):
        nombres = list(Area.objects.values_list("nombre", flat=True))

    assert nombres == ["Salón comunal"]


def test_buscar_por_id_una_fila_de_otro_conjunto_no_la_encuentra(torres, mirador):
    piscina = crear_area(mirador, "Piscina")

    with usar_conjunto(torres.id), pytest.raises(Area.DoesNotExist):
        Area.objects.get(pk=piscina.pk)


def test_consultar_sin_conjunto_activo_falla(torres):
    with usar_conjunto(torres.id):
        pass

    with pytest.raises(SinConjuntoActivo):
        Area.objects.all()


def test_crear_toma_el_conjunto_activo(torres):
    area = crear_area(torres, "Salón comunal")

    assert area.conjunto_id == torres.id


def test_no_se_puede_guardar_en_un_conjunto_distinto_del_activo(torres, mirador):
    with usar_conjunto(torres.id), pytest.raises(EscrituraEnOtroConjunto):
        Area.objects.create(nombre="Piscina", conjunto=mirador)


def test_base_rechaza_reserva_de_un_conjunto_que_apunta_a_un_area_de_otro(torres, mirador):
    piscina = crear_area(mirador, "Piscina")

    with (
        usar_conjunto(torres.id),
        pytest.raises(IntegrityError, match="pruebas_aislamiento_reserva_area_id_conjunto_fk"),
        transaction.atomic(),
    ):
        Reserva.objects.create(area=piscina)


def test_base_rechaza_la_fila_cruzada_aunque_se_salte_save(torres, mirador):
    piscina = crear_area(mirador, "Piscina")

    with (
        usar_conjunto(torres.id),
        pytest.raises(IntegrityError, match="pruebas_aislamiento_reserva_area_id_conjunto_fk"),
        transaction.atomic(),
    ):
        Reserva.objects.bulk_create([Reserva(area_id=piscina.pk, conjunto_id=torres.id)])
