"""Pruebas del modelo Conjunto."""
import uuid

import pytest

from apps.conjuntos.models import Conjunto

pytestmark = pytest.mark.django_db


def test_conjunto_nuevo_nace_activo_y_no_operativo():
    conjunto = Conjunto.objects.create(nombre="Torres del Río")
    conjunto.refresh_from_db()

    assert conjunto.activo is True
    assert conjunto.operativo is False


def test_conjunto_se_identifica_por_uuid():
    conjunto = Conjunto.objects.create(nombre="Torres del Río")

    assert isinstance(conjunto.pk, uuid.UUID)
