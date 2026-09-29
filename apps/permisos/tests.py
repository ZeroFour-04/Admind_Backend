"""Pruebas del catálogo de roles y permisos, del modelo Asignacion y de los permisos efectivos."""
from datetime import date, timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.conjuntos.models import Conjunto
from apps.permisos.catalogo import (
    PERMISOS,
    PERMISOS_DE_PLATAFORMA,
    PERMISOS_POR_ROL,
    PERMISOS_SENSIBLES,
    Rol,
)
from apps.permisos.models import Asignacion
from apps.permisos.servicios import permisos_efectivos
from apps.personas.models import Persona, TipoDocumento

pytestmark = pytest.mark.django_db


@pytest.fixture
def persona():
    return Persona.objects.create(
        tipo_documento=TipoDocumento.CC,
        numero_documento="1023456789",
        nombres="Laura",
        apellidos="Gómez",
    )


@pytest.fixture
def conjunto():
    return Conjunto.objects.create(nombre="Torres del Río")


# Catálogo


def test_cada_rol_tiene_permisos_y_todos_existen_en_el_catalogo():
    assert set(PERMISOS_POR_ROL) == set(Rol.values)
    for permisos in PERMISOS_POR_ROL.values():
        assert permisos <= PERMISOS


def test_permisos_sensibles_existen_en_el_catalogo_e_incluyen_los_de_plataforma():
    assert PERMISOS_SENSIBLES <= PERMISOS
    assert PERMISOS_DE_PLATAFORMA <= PERMISOS_SENSIBLES


def test_superusuario_tiene_todos_los_permisos_del_catalogo():
    permisos = PERMISOS_POR_ROL[Rol.SUPERUSUARIO]

    assert permisos == PERMISOS


def test_administracion_puede_crear_conjuntos_desde_el_conjunto_activo():
    assert "conjunto.crear" in PERMISOS_POR_ROL[Rol.ADMINISTRACION]


def test_administracion_y_superusuario_pueden_aprobar_reservas():
    con_aprobacion = {rol for rol, permisos in PERMISOS_POR_ROL.items() if "reserva.aprobar" in permisos}

    assert con_aprobacion == {Rol.ADMINISTRACION, Rol.SUPERUSUARIO}


def test_secretaria_no_tiene_ningun_permiso_de_aprobacion():
    assert not any(p.endswith(".aprobar") for p in PERMISOS_POR_ROL[Rol.SECRETARIA])


def test_residente_no_tiene_permisos_sensibles():
    assert PERMISOS_POR_ROL[Rol.RESIDENTE].isdisjoint(PERMISOS_SENSIBLES)


# Asignacion


def test_rol_de_conjunto_exige_conjunto(persona):
    with pytest.raises(IntegrityError, match="asignacion_conjunto_segun_alcance"), transaction.atomic():
        Asignacion.objects.create(persona=persona, rol=Rol.RESIDENTE, conjunto=None)


def test_superusuario_se_asigna_sin_conjunto(persona):
    asignacion = Asignacion.objects.create(persona=persona, rol=Rol.SUPERUSUARIO)

    assert asignacion.conjunto is None


def test_superusuario_no_puede_llevar_conjunto(persona, conjunto):
    with pytest.raises(IntegrityError, match="asignacion_conjunto_segun_alcance"), transaction.atomic():
        Asignacion.objects.create(persona=persona, rol=Rol.SUPERUSUARIO, conjunto=conjunto)


def test_rol_fuera_del_catalogo_se_rechaza(persona, conjunto):
    with pytest.raises(IntegrityError, match="asignacion_conjunto_segun_alcance"), transaction.atomic():
        Asignacion.objects.create(persona=persona, rol="operador", conjunto=conjunto)


def test_misma_asignacion_vigente_no_se_repite(persona, conjunto):
    Asignacion.objects.create(persona=persona, rol=Rol.RESIDENTE, conjunto=conjunto)

    with pytest.raises(IntegrityError, match="asignacion_vigente_unica"), transaction.atomic():
        Asignacion.objects.create(persona=persona, rol=Rol.RESIDENTE, conjunto=conjunto)


def test_superusuario_vigente_no_se_repite_aunque_no_tenga_conjunto(persona):
    Asignacion.objects.create(persona=persona, rol=Rol.SUPERUSUARIO)

    with pytest.raises(IntegrityError, match="asignacion_vigente_unica"), transaction.atomic():
        Asignacion.objects.create(persona=persona, rol=Rol.SUPERUSUARIO)


def test_asignacion_cerrada_permite_volver_a_asignar_el_rol(persona, conjunto):
    anterior = Asignacion.objects.create(
        persona=persona, rol=Rol.RESIDENTE, conjunto=conjunto, vigencia_desde=date(2026, 1, 1)
    )
    anterior.vigencia_hasta = date(2026, 6, 30)
    anterior.save()

    Asignacion.objects.create(persona=persona, rol=Rol.RESIDENTE, conjunto=conjunto)

    assert persona.asignaciones.count() == 2


def test_vigencia_no_puede_terminar_antes_de_empezar(persona, conjunto):
    with pytest.raises(IntegrityError, match="asignacion_vigencia_coherente"), transaction.atomic():
        Asignacion.objects.create(
            persona=persona,
            rol=Rol.RESIDENTE,
            conjunto=conjunto,
            vigencia_desde=date(2026, 6, 30),
            vigencia_hasta=date(2026, 1, 1),
        )


def test_persona_con_roles_en_dos_conjuntos_es_un_solo_registro(persona, conjunto):
    """Último criterio de HU-04."""
    otro_conjunto = Conjunto.objects.create(nombre="Mirador")

    Asignacion.objects.create(persona=persona, rol=Rol.RESIDENTE, conjunto=conjunto)
    Asignacion.objects.create(persona=persona, rol=Rol.VIGILANCIA, conjunto=otro_conjunto)

    assert Persona.objects.count() == 1
    assert persona.asignaciones.count() == 2


# Vigencia y permisos efectivos


def test_asignacion_con_vigencia_hasta_hoy_ya_no_esta_vigente(persona, conjunto):
    hoy = timezone.localdate()
    Asignacion.objects.create(
        persona=persona, rol=Rol.RESIDENTE, conjunto=conjunto, vigencia_desde=hoy - timedelta(days=30), vigencia_hasta=hoy
    )

    assert not Asignacion.objects.vigentes().exists()


def test_asignacion_que_empieza_manana_todavia_no_esta_vigente(persona, conjunto):
    Asignacion.objects.create(
        persona=persona, rol=Rol.RESIDENTE, conjunto=conjunto, vigencia_desde=timezone.localdate() + timedelta(days=1)
    )

    assert not Asignacion.objects.vigentes().exists()


def test_permisos_efectivos_son_la_union_de_los_roles_en_el_conjunto(persona, conjunto):
    Asignacion.objects.create(persona=persona, rol=Rol.CONSEJO, conjunto=conjunto)
    Asignacion.objects.create(persona=persona, rol=Rol.RESIDENTE, conjunto=conjunto)

    esperados = PERMISOS_POR_ROL[Rol.CONSEJO] | PERMISOS_POR_ROL[Rol.RESIDENTE]
    assert permisos_efectivos(persona, conjunto.id) == esperados


def test_rol_de_un_conjunto_no_da_permisos_en_otro(persona, conjunto):
    otro_conjunto = Conjunto.objects.create(nombre="Mirador")
    Asignacion.objects.create(persona=persona, rol=Rol.ADMINISTRACION, conjunto=conjunto)

    assert permisos_efectivos(persona, otro_conjunto.id) == set()


def test_superusuario_tiene_todos_los_permisos_en_cualquier_conjunto_y_sin_conjunto(persona, conjunto):
    Asignacion.objects.create(persona=persona, rol=Rol.SUPERUSUARIO)
    Asignacion.objects.create(persona=persona, rol=Rol.RESIDENTE, conjunto=conjunto)

    assert permisos_efectivos(persona, None) == PERMISOS
    assert permisos_efectivos(persona, conjunto.id) == PERMISOS
