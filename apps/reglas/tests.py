"""Pruebas de HU-10 (reglas por niveles, catálogo cerrado y versionado) y del evaluador de HU-13."""
from datetime import time, timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APIClient

from apps.areas.models import Area
from apps.auditoria.models import Registro
from apps.comun.aislamiento.contexto import usar_conjunto
from apps.conjuntos.models import Conjunto
from apps.conjuntos.servicios import requisitos_para_operar
from apps.cuentas.models import TokenDeSesion, Usuario
from apps.permisos.catalogo import Rol
from apps.permisos.models import Asignacion
from apps.personas.models import Persona, TipoDocumento
from apps.reglas import mora, servicios
from apps.reglas.evaluador import EVALUADOR_POR_TIPO, aforo, dias_que_no_abre, evaluar
from apps.reglas.models import Regla
from apps.reservas.models import Solicitud
from apps.unidades.models import Unidad

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


def crear_area(conjunto, nombre):
    with usar_conjunto(conjunto.id):
        return Area.objects.create(
            nombre=nombre, hora_apertura=time(8), hora_cierre=time(22), duracion_franja_minutos=240, aforo_maximo=50,
        )


@pytest.fixture
def salon(torres):
    return crear_area(torres, "Salón comunal")


def crear(cliente, tipo, parametros, area=None, **extra):
    datos = {"tipo": tipo, "parametros": parametros, "vigencia_desde": str(HOY()), **extra}
    if area is not None:
        datos["area"] = str(area.id)
    return cliente.post("/reglas/", datos, format="json")


def hay_reglas(conjunto):
    with usar_conjunto(conjunto.id):
        return Regla.objects.exists()


DE_UN_AREA = {"DIAS_QUE_NO_ABRE", "CUPO_POR_UNIDAD"}
NAVIDAD = {"desde": "2026-12-25", "hasta": "2026-12-25", "motivo": "Navidad"}
PARAMETROS_VALIDOS = {
    "ANTICIPACION_MINIMA": ({"horas": 24}, "Se solicita con al menos 24 horas de anticipación"),
    "ANTICIPACION_MAXIMA": ({"dias": 30}, "Se solicita con máximo 30 días de anticipación"),
    "REQUIERE_PAZ_Y_SALVO": ({}, "Requiere estar a paz y salvo con la administración"),
    "CUPO_POR_UNIDAD": ({"reservas": 2, "dias": 30}, "Máximo 2 reservas por apartamento cada 30 días"),
    "DIAS_QUE_NO_ABRE": (
        {"renglones": [NAVIDAD, {"dia_semana": 0, "motivo": " Limpieza "}]},
        "No abre los lunes (Limpieza); el 25 de diciembre de 2026 (Navidad)",
    ),
}


# Criterios de aceptación


def test_sin_reglas_el_conjunto_no_puede_quedar_operativo(admin, torres):
    def reglas_cumplidas():
        with usar_conjunto(torres.id):
            return next(r for r in requisitos_para_operar(torres) if r.clave == "reglas_del_conjunto").cumplido

    assert reglas_cumplidas() is False
    # La que todo conjunto necesita es la anticipación máxima: otra regla del conjunto no basta.
    crear(admin, "ANTICIPACION_MINIMA", {"horas": 24})
    assert reglas_cumplidas() is False
    crear(admin, "ANTICIPACION_MAXIMA", {"dias": 30})
    assert reglas_cumplidas() is True


@pytest.mark.parametrize("falta", ["area", "tipo", "parametros", "vigencia_desde"])
def test_una_regla_exige_tipo_parametros_area_y_vigencia(admin, torres, salon, falta):
    datos = {
        "area": str(salon.id), "tipo": "CUPO_POR_UNIDAD", "parametros": {"reservas": 2, "dias": 30},
        "vigencia_desde": str(HOY()),
    }
    del datos[falta]

    respuesta = admin.post("/reglas/", datos, format="json")

    assert respuesta.status_code == 400
    assert falta in respuesta.json()
    assert not hay_reglas(torres)


def test_una_regla_permisiva_se_rechaza(admin, torres):
    assert crear(admin, "ANTICIPACION_MINIMA", {"horas": -1}).status_code == 400
    assert "tipo" in crear(admin, "PERMITIR_X", {}).json()
    assert not hay_reglas(torres)


def test_una_regla_editada_deja_version_autor_y_fecha(admin, laura, torres):
    original = crear(admin, "ANTICIPACION_MAXIMA", {"dias": 30}).json()

    respuesta = admin.patch(f"/reglas/{original['id']}/", {"parametros": {"dias": 15}}, format="json")

    nueva = respuesta.json()
    assert respuesta.status_code == 200
    assert nueva["id"] != original["id"]
    assert (nueva["reemplaza"], nueva["descripcion"]) == (
        original["id"], "Se solicita con máximo 15 días de anticipación"
    )
    assert nueva["creada_por"] == "Laura Gómez" and nueva["creada_en"]
    with usar_conjunto(torres.id):
        anterior = Regla.objects.get(pk=original["id"])
        registro = Registro.objects.get(accion="regla.editar")
        vigentes = list(Regla.objects.vigentes())
    assert anterior.vigencia_hasta == HOY()
    assert anterior.parametros == {"dias": 30}
    assert [regla.parametros for regla in vigentes] == [{"dias": 15}]
    assert (registro.actor_id, registro.antes["parametros"], registro.despues["parametros"]) == (
        laura.id, {"dias": 30}, {"dias": 15}
    )


# Catálogo y niveles


@pytest.mark.parametrize("tipo", sorted(PARAMETROS_VALIDOS))
def test_cada_tipo_del_catalogo_se_crea_y_se_describe_en_palabras(admin, salon, tipo):
    parametros, descripcion = PARAMETROS_VALIDOS[tipo]
    de_un_area = tipo in DE_UN_AREA

    respuesta = crear(admin, tipo, parametros, salon if de_un_area else None)

    assert respuesta.status_code == 201
    assert respuesta.json()["descripcion"] == descripcion
    if de_un_area:
        assert respuesta.json()["area"] == {"id": str(salon.id), "nombre": "Salón comunal"}
        assert respuesta.json()["nivel"] == "beta"
    else:
        assert respuesta.json()["area"] is None
        assert respuesta.json()["nivel"] == "alfa"


@pytest.mark.parametrize(
    ("tipo", "parametros", "campo"),
    [
        ("ANTICIPACION_MINIMA", {"horas": 24, "minutos": 2}, "minutos"),
        ("ANTICIPACION_MINIMA", {"horas": "24"}, "horas"),
        ("ANTICIPACION_MAXIMA", {"dias": 0}, "dias"),
        ("CUPO_POR_UNIDAD", {"reservas": 2}, "dias"),
        ("DIAS_QUE_NO_ABRE", {"renglones": []}, "renglones"),
        ("DIAS_QUE_NO_ABRE", {"renglones": [{"dia_semana": 0}]}, "renglones"),
        ("DIAS_QUE_NO_ABRE", {"renglones": [{"dia_semana": 7, "motivo": "Limpieza"}]}, "renglones"),
        (
            "DIAS_QUE_NO_ABRE",
            {"renglones": [{"desde": "2026-12-25", "hasta": "2026-12-24", "motivo": "Navidad"}]},
            "renglones",
        ),
        (
            "DIAS_QUE_NO_ABRE",
            {"renglones": [{"desde": "25/12/2026", "hasta": "25/12/2026", "motivo": "Navidad"}]},
            "renglones",
        ),
    ],
)
def test_parametros_de_mas_o_equivocados_se_rechazan(admin, salon, tipo, parametros, campo):
    respuesta = crear(admin, tipo, parametros, salon if tipo in DE_UN_AREA else None)

    assert respuesta.status_code == 400
    assert campo in respuesta.json()


def test_no_se_crea_una_regla_sobre_un_area_de_otro_conjunto(admin):
    mirador = Conjunto.objects.create(nombre="Mirador")
    ajena = crear_area(mirador, "Piscina")

    respuesta = crear(admin, "CUPO_POR_UNIDAD", {"reservas": 2, "dias": 30}, ajena)

    assert respuesta.json() == {"area": ["Esa área no existe en este conjunto."]}


def test_una_regla_no_se_define_dos_veces(admin, torres, salon):
    bbq = crear_area(torres, "BBQ")
    cupo = {"reservas": 2, "dias": 30}

    assert crear(admin, "ANTICIPACION_MINIMA", {"horas": 24}).status_code == 201
    assert crear(admin, "ANTICIPACION_MINIMA", {"horas": 48}).status_code == 409
    primera = crear(admin, "CUPO_POR_UNIDAD", cupo, salon)
    assert crear(admin, "CUPO_POR_UNIDAD", cupo, salon).status_code == 409
    # En otra área sí, y en la misma después de retirar la que había.
    assert crear(admin, "CUPO_POR_UNIDAD", cupo, bbq).status_code == 201
    admin.post(f"/reglas/{primera.json()['id']}/retirar/")
    assert crear(admin, "CUPO_POR_UNIDAD", cupo, salon).status_code == 201


def test_una_regla_del_conjunto_no_lleva_area_y_una_de_un_area_la_exige(admin, torres, salon):
    con_area_de_mas = crear(admin, "ANTICIPACION_MINIMA", {"horas": 24}, salon)
    sin_area = crear(admin, "CUPO_POR_UNIDAD", {"reservas": 2, "dias": 30})

    assert (con_area_de_mas.status_code, con_area_de_mas.json()) == (
        400, {"area": ["Esta regla es del conjunto: no lleva área."]}
    )
    assert (sin_area.status_code, sin_area.json()) == (400, {"area": ["Esta regla es de un área: elige cuál."]})
    assert not hay_reglas(torres)


@pytest.mark.parametrize(
    ("tipo", "parametros"),
    [
        ("AFORO", {"maximo": 25}),
        ("FRANJA_HORARIA", {"dias_semana": [5, 6], "desde": "10:00", "hasta": "18:00"}),
        ("DIAS_NO_RESERVABLES", {"dias_semana": [0], "fechas": ["2026-12-25"]}),
    ],
)
def test_los_tipos_retirados_ya_no_se_crean(admin, torres, salon, tipo, parametros):
    respuesta = crear(admin, tipo, parametros, salon)

    assert respuesta.status_code == 400
    assert "tipo" in respuesta.json()
    assert not hay_reglas(torres)


def test_una_regla_retirada_del_historial_se_sigue_leyendo(admin, torres, salon, laura):
    with usar_conjunto(torres.id):
        vieja = Regla.objects.create(
            area=salon, tipo="AFORO", parametros={"maximo": 25}, vigencia_hasta=HOY(), creada_por=laura
        )

    respuesta = admin.get(f"/reglas/{vieja.id}/")

    assert respuesta.status_code == 200
    assert (respuesta.json()["descripcion"], respuesta.json()["nivel"]) == ("Máximo 25 asistentes", None)
    assert admin.get("/reglas/").json() == []


def test_el_catalogo_trae_cada_tipo_con_su_nivel_y_su_descripcion(admin):
    respuesta = admin.get("/reglas/catalogo/")

    catalogo = respuesta.json()
    assert respuesta.status_code == 200
    assert [(entrada["tipo"], entrada["nivel"]) for entrada in catalogo] == [
        ("ANTICIPACION_MINIMA", "alfa"),
        ("ANTICIPACION_MAXIMA", "alfa"),
        ("REQUIERE_PAZ_Y_SALVO", "alfa"),
        ("DIAS_QUE_NO_ABRE", "beta"),
        ("CUPO_POR_UNIDAD", "beta"),
    ]
    assert all(entrada["nombre"] and entrada["descripcion"] for entrada in catalogo)
    assert catalogo[2]["nota"] == "Todavía no restringe: falta el módulo de pagos."
    assert catalogo[4]["nombre"] == "Límite de reservas por apartamento" and catalogo[4]["nota"] == ""


# Lo que hace cumplir la base, aunque alguien se salte el servicio


def test_la_base_no_deja_dos_reglas_abiertas_del_mismo_tipo(torres, salon, laura):
    cupo = {"reservas": 2, "dias": 30}
    with usar_conjunto(torres.id):
        Regla.objects.create(tipo="ANTICIPACION_MINIMA", parametros={"horas": 24}, creada_por=laura)
        Regla.objects.create(area=salon, tipo="CUPO_POR_UNIDAD", parametros=cupo, creada_por=laura)
        with pytest.raises(IntegrityError), transaction.atomic():
            Regla.objects.create(tipo="ANTICIPACION_MINIMA", parametros={"horas": 48}, creada_por=laura)
        with pytest.raises(IntegrityError), transaction.atomic():
            Regla.objects.create(area=salon, tipo="CUPO_POR_UNIDAD", parametros=cupo, creada_por=laura)


def test_la_base_no_deja_una_regla_abierta_en_el_nivel_equivocado(torres, salon, laura):
    with usar_conjunto(torres.id):
        with pytest.raises(IntegrityError), transaction.atomic():
            Regla.objects.create(area=salon, tipo="ANTICIPACION_MINIMA", parametros={"horas": 24}, creada_por=laura)
        with pytest.raises(IntegrityError), transaction.atomic():
            Regla.objects.create(tipo="CUPO_POR_UNIDAD", parametros={"reservas": 2, "dias": 30}, creada_por=laura)
        # Una regla cerrada es historial: conserva la forma que tuvo, aunque su tipo ya no exista.
        Regla.objects.create(
            area=salon, tipo="AFORO", parametros={"maximo": 25}, vigencia_hasta=HOY(), creada_por=laura
        )
        assert Regla.objects.count() == 1


# Retiro y permisos


def test_retirar_cierra_la_vigencia_y_la_conserva(admin):
    regla = crear(admin, "ANTICIPACION_MINIMA", {"horas": 24}).json()

    respuesta = admin.post(f"/reglas/{regla['id']}/retirar/")

    assert respuesta.status_code == 200
    assert respuesta.json()["vigencia_hasta"] == str(HOY())
    assert admin.get("/reglas/").json() == []
    assert admin.get(f"/reglas/{regla['id']}/").status_code == 200
    assert admin.post(f"/reglas/{regla['id']}/retirar/").status_code == 409
    assert admin.patch(f"/reglas/{regla['id']}/", {"parametros": {"horas": 48}}, format="json").status_code == 409
    assert admin.delete(f"/reglas/{regla['id']}/").status_code == 405


def test_una_regla_que_empieza_despues_aparece_en_el_listado_y_no_esta_vigente_hoy(admin, torres):
    manana = HOY() + timedelta(days=1)
    crear(admin, "ANTICIPACION_MINIMA", {"horas": 24}, vigencia_desde=str(manana))

    assert len(admin.get("/reglas/").json()) == 1
    with usar_conjunto(torres.id):
        assert not Regla.objects.vigentes().exists()
        assert Regla.objects.vigentes(manana).exists()


def test_sin_regla_configurar_no_se_crea_ni_se_ve(torres):
    crear_usuario("vecino@torres.com", Rol.RESIDENTE, torres)
    residente = cliente_para("vecino@torres.com")

    assert residente.get("/reglas/").status_code == 403
    assert residente.get("/reglas/catalogo/").status_code == 403
    assert crear(residente, "ANTICIPACION_MINIMA", {"horas": 24}).status_code == 403


# Evaluador (HU-13): una prueba que cumple y una que no por cada tipo del catálogo.

EN_DIEZ_DIAS = HOY() + timedelta(days=10)
DIA = EN_DIEZ_DIAS.weekday()
OTRO_DIA = (DIA + 1) % 7


@pytest.fixture
def solicitud(torres, salon, laura):
    """Una solicitud en memoria: 20 asistentes, en diez días, de 8:00 a 12:00, a nombre del 101."""
    with usar_conjunto(torres.id):
        unidad = Unidad.objects.create(nombre="Torre 1 – 101")
    return Solicitud(
        conjunto=torres, area=salon, unidad=unidad, persona=laura, fecha=EN_DIEZ_DIAS,
        hora_inicio=time(8), hora_fin=time(12), asistentes=20,
    )


@pytest.mark.parametrize(
    ("tipo", "cumple", "no_cumple"),
    [
        ("ANTICIPACION_MINIMA", {"horas": 24}, {"horas": 24 * 20}),
        ("ANTICIPACION_MAXIMA", {"dias": 30}, {"dias": 5}),
        (
            "DIAS_QUE_NO_ABRE",
            {"renglones": [{"dia_semana": OTRO_DIA, "motivo": "Limpieza"}]},
            {"renglones": [
                {"desde": EN_DIEZ_DIAS.isoformat(), "hasta": EN_DIEZ_DIAS.isoformat(), "motivo": "Reparación"}
            ]},
        ),
    ],
)
def test_cada_tipo_cumple_o_no_segun_sus_parametros(torres, solicitud, tipo, cumple, no_cumple):
    evaluar_tipo = EVALUADOR_POR_TIPO[tipo]

    with usar_conjunto(torres.id):
        assert evaluar_tipo(solicitud, cumple) == ""
        assert evaluar_tipo(solicitud, no_cumple) != ""


def test_el_cupo_por_unidad_cuenta_las_apartadas_de_la_ventana(torres, solicitud, laura):
    with usar_conjunto(torres.id):
        assert EVALUADOR_POR_TIPO["CUPO_POR_UNIDAD"](solicitud, {"reservas": 1, "dias": 30}) == ""
        Solicitud.objects.create(
            area=solicitud.area, unidad=solicitud.unidad, persona=laura, fecha=EN_DIEZ_DIAS - timedelta(days=3),
            hora_inicio=time(8), hora_fin=time(12), estado="APARTADA", bloqueo_vence_en=timezone.now(),
        )

        motivo = EVALUADOR_POR_TIPO["CUPO_POR_UNIDAD"](solicitud, {"reservas": 1, "dias": 30})
        fuera_de_la_ventana = EVALUADOR_POR_TIPO["CUPO_POR_UNIDAD"](solicitud, {"reservas": 1, "dias": 2})

    assert motivo == "Este apartamento ya tiene 1 reservas de esta área en 30 días; el máximo es 1."
    assert fuera_de_la_ventana == ""


def test_paz_y_salvo_restringe_a_la_unidad_en_mora(monkeypatch, torres, solicitud):
    evaluar_tipo = EVALUADOR_POR_TIPO["REQUIERE_PAZ_Y_SALVO"]
    assert evaluar_tipo(solicitud, {}) == ""

    monkeypatch.setattr(mora, "unidad_en_mora", lambda unidad: True)

    assert evaluar_tipo(solicitud, {}) == "El apartamento no está a paz y salvo con la administración."


def test_el_aforo_se_explica_en_la_voz_de_la_interfaz(solicitud):
    solicitud.area.aforo_maximo = 25
    solicitud.asistentes = 40

    assert aforo(solicitud).motivo == "Esta área admite máximo 25 asistentes y la solicitud dice 40."


def test_el_motivo_de_un_dia_que_no_abre_llega_al_residente(solicitud):
    renglones = [
        {"dia_semana": DIA, "motivo": "Limpieza"},
        {"dia_semana": OTRO_DIA, "motivo": "Fumigación"},
        {
            "desde": (EN_DIEZ_DIAS - timedelta(days=2)).isoformat(),
            "hasta": (EN_DIEZ_DIAS + timedelta(days=20)).isoformat(),
            "motivo": "Cambio del piso",
        },
    ]

    assert dias_que_no_abre(solicitud, {"renglones": renglones}) == (
        "Esta área no abre ese día: Limpieza; Cambio del piso."
    )


def test_un_cierre_cuenta_las_reservas_apartadas_que_quedan_dentro(admin, torres, solicitud, laura):
    """Cerrar un día no cancela lo ya apartado: el sistema solo avisa cuántas quedaron dentro (plan D2 a)."""
    cierre = [{
        "desde": (EN_DIEZ_DIAS - timedelta(days=1)).isoformat(),
        "hasta": (EN_DIEZ_DIAS + timedelta(days=1)).isoformat(),
        "motivo": "Cambio del piso",
    }]

    def crear_solicitud(fecha, hora, estado):
        return Solicitud.objects.create(
            area=solicitud.area, unidad=solicitud.unidad, persona=laura, fecha=fecha,
            hora_inicio=time(hora), hora_fin=time(hora + 4), estado=estado, bloqueo_vence_en=timezone.now(),
        )

    with usar_conjunto(torres.id):
        crear_solicitud(EN_DIEZ_DIAS, 8, "APARTADA")
        crear_solicitud(EN_DIEZ_DIAS, 12, "LIBERADA")
        crear_solicitud(EN_DIEZ_DIAS + timedelta(days=5), 8, "APARTADA")
        dentro = servicios.reservas_en_cierre(solicitud.area, cierre)
        otro_dia = servicios.reservas_en_cierre(solicitud.area, [{"dia_semana": OTRO_DIA, "motivo": "Limpieza"}])
    regla = crear(admin, "DIAS_QUE_NO_ABRE", {"renglones": cierre}, solicitud.area).json()

    assert (dentro, otro_dia) == (1, 0)
    assert regla["reservas_afectadas"] == 1
    assert [r["reservas_afectadas"] for r in admin.get("/reglas/").json()] == [1]


def test_el_evaluador_no_se_detiene_en_la_primera_falla(torres, solicitud, laura):
    """El AND sin precedencias de HU-10: dos reglas incumplidas son dos motivos."""
    solicitud.area.aforo_maximo = 25
    solicitud.asistentes = 40
    with usar_conjunto(torres.id):
        Regla.objects.create(tipo="ANTICIPACION_MAXIMA", parametros={"dias": 5}, creada_por=laura)
        resultados = evaluar(solicitud)

    fallas = [resultado.clave for resultado in resultados if not resultado.cumple]
    assert sorted(fallas) == ["AFORO", "ANTICIPACION_MAXIMA", "RESIDE"]
    assert [resultado.clave for resultado in resultados[:4]] == [
        "RESIDE", "NO_EN_EL_PASADO", "AREA_DISPONIBLE", "AFORO",
    ]
    assert [resultado.nivel for resultado in resultados] == ["sistema", "sistema", "sistema", "beta", "alfa"]


def test_una_regla_del_conjunto_se_evalua_en_todas_las_areas(torres, solicitud, laura):
    with usar_conjunto(torres.id):
        Regla.objects.create(tipo="ANTICIPACION_MAXIMA", parametros={"dias": 5}, creada_por=laura)
        en_el_salon = evaluar(solicitud)
        solicitud.area = Area.objects.create(
            nombre="BBQ", hora_apertura=time(8), hora_cierre=time(22), duracion_franja_minutos=240, aforo_maximo=50
        )
        en_el_bbq = evaluar(solicitud)

    for resultados in (en_el_salon, en_el_bbq):
        regla = next(resultado for resultado in resultados if resultado.clave == "ANTICIPACION_MAXIMA")
        assert (regla.cumple, regla.nivel) == (False, "alfa")
