from datetime import time
from uuid import uuid4

import pytest

from apps.areas.models import Area, ModoDeUso
from apps.comun.aislamiento.contexto import usar_conjunto
from apps.conjuntos.models import Conjunto
from apps.personas.models import Persona, TipoDocumento
from apps.unidades.models import Unidad


@pytest.fixture
def conjunto():
    return Conjunto.objects.create(nombre="Conjunto de pruebas")


@pytest.fixture
def conjunto_ajeno():
    return Conjunto.objects.create(nombre="Conjunto ajeno")


@pytest.fixture
def persona_factory():
    def crear(nombre="Persona de prueba"):
        return Persona.objects.create(
            tipo_documento=TipoDocumento.CC,
            numero_documento=uuid4().hex[:12].upper(),
            nombres=nombre,
            apellidos="Prueba",
        )

    return crear


@pytest.fixture
def unidad_factory():
    def crear(conjunto, nombre="Vivienda de prueba"):
        with usar_conjunto(conjunto.id):
            return Unidad.objects.create(nombre=f"{nombre} {uuid4().hex[:6]}")

    return crear


@pytest.fixture
def area_factory():
    def crear(conjunto, nombre="Area de prueba", modo=ModoDeUso.RESERVA):
        datos = {
            "hora_apertura": time(8),
            "hora_cierre": time(22),
            "modo_uso": modo,
            "duracion_franja_minutos": 120 if modo == ModoDeUso.RESERVA else None,
            "permanencia_maxima_minutos": 60 if modo == ModoDeUso.INGRESO else None,
            "aforo_maximo": 20,
        }
        with usar_conjunto(conjunto.id):
            return Area.objects.create(nombre=f"{nombre} {uuid4().hex[:6]}", **datos)

    return crear
