"""Pruebas de HU-10: reglas beta de reserva, su catálogo cerrado y su versionado.

El AND sin precedencias (dos reglas incumplidas → dos motivos) se prueba con el evaluador, en HU-13.
"""
from datetime import time, timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.areas.models import Area, Clasificacion
from apps.auditoria.models import Registro
from apps.comun.aislamiento.contexto import usar_conjunto
from apps.conjuntos.models import Conjunto
from apps.conjuntos.servicios import requisitos_para_operar
from apps.cuentas.models import TokenDeSesion, Usuario
from apps.permisos.catalogo import Rol
from apps.permisos.models import Asignacion
from apps.personas.models import Persona, TipoDocumento
from apps.reglas.models import Regla

pytestmark = pytest.mark.django_db

CONTRASENA = "una-clave-larga-2026"
HOY = timezone.localdate


def crear_usuario(correo, rol, conjunto):
    persona = Persona.objects.create(
        tipo_documento=TipoDocumento.CC,
        numero_documento=str(Persona.objects.count() + 1023456789),
        nombres="Laura",
        apellidos="Gómez",
    )
    Asignacion.objects.create(persona=persona, rol=rol, conjunto=conjunto)
    Usuario.objects.create_user(correo, CONTRASENA, persona)
    return persona


def cliente_para(correo):
    """Sesión con el segundo factor dado por verificado: su flujo se prueba en cuentas."""
    cliente = APIClient()
    respuesta = cliente.post("/auth/login/", {"correo": correo, "contrasena": CONTRASENA}, format="json")
    cliente.credentials(HTTP_AUTHORIZATION=f"Token {respuesta.json()['token']}")
    TokenDeSesion.objects.filter(usuario__correo=correo).update(dos_factores_verificado=True)
    return cliente


@pytest.fixture
def torres():
    return Conjunto.objects.create(nombre="Torres del Río")


@pytest.fixture
def laura(torres):
    return crear_usuario("admin@torres.com", Rol.ADMINISTRACION, torres)


@pytest.fixture
def admin(laura):
    return cliente_para("admin@torres.com")


def crear_area(conjunto, nombre, clasificacion=Clasificacion.COMUN):
    with usar_conjunto(conjunto.id):
        return Area.objects.create(
            nombre=nombre, clasificacion=clasificacion, hora_apertura=time(8), hora_cierre=time(22),
            duracion_franja_minutos=240,
        )


@pytest.fixture
def salon(torres):
    return crear_area(torres, "Salón comunal")


def crear(cliente, area, tipo, parametros, **extra):
    datos = {"area": str(area.id), "tipo": tipo, "parametros": parametros, "vigencia_desde": str(HOY()), **extra}
    return cliente.post("/reglas/", datos, format="json")


def hay_reglas(area):
    with usar_conjunto(area.conjunto_id):
        return Regla.objects.exists()


PARAMETROS_VALIDOS = {
    "ANTICIPACION_MINIMA": ({"horas": 24}, "Se solicita con al menos 24 horas de anticipación"),
    "ANTICIPACION_MAXIMA": ({"dias": 30}, "Se solicita con máximo 30 días de anticipación"),
    "CUPO_POR_UNIDAD": ({"reservas": 2, "dias": 30}, "Máximo 2 reservas por apartamento cada 30 días"),
    "AFORO": ({"maximo": 25}, "Máximo 25 asistentes"),
    "FRANJA_HORARIA": ({"dias_semana": [5, 6], "desde": "10:00", "hasta": "18:00"}, "Solo los sábados y domingos, de 10:00 a 18:00"),
    "DIAS_NO_RESERVABLES": ({"dias_semana": [0], "fechas": ["2026-12-25"]}, "No se reserva los lunes ni el 2026-12-25"),
    "REQUIERE_PAZ_Y_SALVO": ({}, "Requiere estar a paz y salvo con la administración"),
}


# Criterios de aceptación


def test_sin_reglas_el_conjunto_no_puede_quedar_operativo(admin, torres, salon):
    def reglas_cumplidas():
        with usar_conjunto(torres.id):
            return next(r for r in requisitos_para_operar(torres) if r.clave == "reglas_beta").cumplido

    assert reglas_cumplidas() is False
    crear(admin, salon, "AFORO", {"maximo": 25})
    assert reglas_cumplidas() is True


@pytest.mark.parametrize("falta", ["area", "tipo", "parametros", "vigencia_desde"])
def test_una_regla_exige_tipo_parametros_area_y_vigencia(admin, salon, falta):
    datos = {"area": str(salon.id), "tipo": "AFORO", "parametros": {"maximo": 25}, "vigencia_desde": str(HOY())}
    del datos[falta]

    respuesta = admin.post("/reglas/", datos, format="json")

    assert respuesta.status_code == 400
    assert falta in respuesta.json()
    assert not hay_reglas(salon)


def test_una_regla_permisiva_se_rechaza(admin, salon):
    assert crear(admin, salon, "ANTICIPACION_MINIMA", {"horas": -1}).status_code == 400
    assert "tipo" in crear(admin, salon, "PERMITIR_X", {}).json()
    assert not hay_reglas(salon)


def test_una_regla_beta_no_relaja_una_alfa(admin, torres, salon):
    porteria = crear_area(torres, "Portería", Clasificacion.COMUN_ESENCIAL)

    respuesta = crear(admin, porteria, "REQUIERE_PAZ_Y_SALVO", {})

    assert respuesta.status_code == 400
    assert respuesta.json()["parametros"] == ["Un área común esencial no se puede restringir por mora."]
    assert crear(admin, salon, "REQUIERE_PAZ_Y_SALVO", {}).status_code == 201


def test_una_regla_editada_deja_version_autor_y_fecha(admin, laura, torres, salon):
    original = crear(admin, salon, "AFORO", {"maximo": 25}).json()

    respuesta = admin.patch(f"/reglas/{original['id']}/", {"parametros": {"maximo": 30}}, format="json")

    nueva = respuesta.json()
    assert respuesta.status_code == 200
    assert nueva["id"] != original["id"]
    assert (nueva["reemplaza"], nueva["descripcion"]) == (original["id"], "Máximo 30 asistentes")
    assert nueva["creada_por"] == "Laura Gómez" and nueva["creada_en"]
    with usar_conjunto(torres.id):
        anterior = Regla.objects.get(pk=original["id"])
        registro = Registro.objects.get(accion="regla.editar")
        vigentes = list(Regla.objects.vigentes())
    assert anterior.vigencia_hasta == HOY()
    assert anterior.parametros == {"maximo": 25}
    assert [regla.parametros for regla in vigentes] == [{"maximo": 30}]
    assert (registro.actor_id, registro.antes["parametros"], registro.despues["parametros"]) == (
        laura.id, {"maximo": 25}, {"maximo": 30}
    )


# Catálogo


@pytest.mark.parametrize("tipo", sorted(PARAMETROS_VALIDOS))
def test_cada_tipo_del_catalogo_se_crea_y_se_describe_en_palabras(admin, salon, tipo):
    parametros, descripcion = PARAMETROS_VALIDOS[tipo]

    respuesta = crear(admin, salon, tipo, parametros)

    assert respuesta.status_code == 201
    assert respuesta.json()["descripcion"] == descripcion
    assert respuesta.json()["area"] == {"id": str(salon.id), "nombre": "Salón comunal"}


@pytest.mark.parametrize(
    ("tipo", "parametros", "campo"),
    [
        ("AFORO", {"maximo": 25, "minimo": 2}, "minimo"),
        ("AFORO", {"maximo": "25"}, "maximo"),
        ("AFORO", {"maximo": 0}, "maximo"),
        ("ANTICIPACION_MAXIMA", {"dias": 0}, "dias"),
        ("CUPO_POR_UNIDAD", {"reservas": 2}, "dias"),
        ("FRANJA_HORARIA", {"dias_semana": [], "desde": "10:00", "hasta": "18:00"}, "dias_semana"),
        ("FRANJA_HORARIA", {"dias_semana": [7], "desde": "10:00", "hasta": "18:00"}, "dias_semana"),
        ("FRANJA_HORARIA", {"dias_semana": [5], "desde": "18:00", "hasta": "10:00"}, "hasta"),
        ("DIAS_NO_RESERVABLES", {"dias_semana": [], "fechas": []}, "parametros"),
        ("DIAS_NO_RESERVABLES", {"dias_semana": [], "fechas": ["25/12/2026"]}, "fechas"),
    ],
)
def test_parametros_de_mas_o_equivocados_se_rechazan(admin, salon, tipo, parametros, campo):
    respuesta = crear(admin, salon, tipo, parametros)

    assert respuesta.status_code == 400
    assert campo in respuesta.json()


def test_no_se_crea_una_regla_sobre_un_area_de_otro_conjunto(admin):
    mirador = Conjunto.objects.create(nombre="Mirador")
    ajena = crear_area(mirador, "Piscina")

    respuesta = crear(admin, ajena, "AFORO", {"maximo": 25})

    assert respuesta.json() == {"area": ["Esa área no existe en este conjunto."]}


# Retiro y permisos


def test_retirar_cierra_la_vigencia_y_la_conserva(admin, torres, salon):
    regla = crear(admin, salon, "AFORO", {"maximo": 25}).json()

    respuesta = admin.post(f"/reglas/{regla['id']}/retirar/")

    assert respuesta.status_code == 200
    assert respuesta.json()["vigencia_hasta"] == str(HOY())
    assert admin.get("/reglas/").json() == []
    assert admin.get(f"/reglas/{regla['id']}/").status_code == 200
    assert admin.post(f"/reglas/{regla['id']}/retirar/").status_code == 409
    assert admin.patch(f"/reglas/{regla['id']}/", {"parametros": {"maximo": 30}}, format="json").status_code == 409
    assert admin.delete(f"/reglas/{regla['id']}/").status_code == 405


def test_una_regla_que_empieza_despues_aparece_en_el_listado_y_no_esta_vigente_hoy(admin, torres, salon):
    manana = HOY() + timedelta(days=1)
    crear(admin, salon, "AFORO", {"maximo": 25}, vigencia_desde=str(manana))

    assert len(admin.get("/reglas/").json()) == 1
    with usar_conjunto(torres.id):
        assert not Regla.objects.vigentes().exists()
        assert Regla.objects.vigentes(manana).exists()


def test_sin_regla_configurar_no_se_crea_ni_se_ve(torres, salon):
    crear_usuario("vecino@torres.com", Rol.RESIDENTE, torres)
    residente = cliente_para("vecino@torres.com")

    assert residente.get("/reglas/").status_code == 403
    assert crear(residente, salon, "AFORO", {"maximo": 25}).status_code == 403
