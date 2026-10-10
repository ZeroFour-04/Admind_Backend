"""Pruebas del servicio de ingresos a zonas con aforo simultáneo (plan de zonas con ingreso, F3).

Se llama al servicio directamente, sin HTTP. La hora la fija cada prueba con `ahora`.
"""
from datetime import datetime, time, timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APIClient

from apps.areas.models import Area
from apps.auditoria.models import Registro
from apps.comun.aislamiento.contexto import usar_conjunto
from apps.conjuntos.models import Conjunto
from apps.cuentas.models import TokenDeSesion, Usuario
from apps.ingresos import servicios
from apps.ingresos.models import EstadoIngreso, Ingreso
from apps.notificaciones.models import Notificacion
from apps.permisos.catalogo import PERMISOS_POR_ROL, PERMISOS_SENSIBLES, Rol
from apps.permisos.models import Asignacion
from apps.personas.models import Persona, TipoDocumento
from apps.reglas import servicios as reglas
from apps.unidades.models import TipoVinculo, Unidad, VinculoUnidad

pytestmark = pytest.mark.django_db

AHORA = timezone.make_aware(datetime.combine(timezone.localdate(), time(10)))


def persona(nombres, numero, tipo=TipoDocumento.CC):
    return Persona.objects.create(tipo_documento=tipo, numero_documento=numero, nombres=nombres, apellidos="Gómez")


def crear_area(conjunto, nombre="Gimnasio", **extra):
    datos = {
        "modo_uso": "ingreso",
        "hora_apertura": time(5),
        "hora_cierre": time(22),
        "duracion_franja_minutos": None,
        "permanencia_maxima_minutos": 60,
        "aforo_maximo": 3,
        **extra,
    }
    with usar_conjunto(conjunto.id):
        return Area.objects.create(nombre=nombre, **datos)


def vivienda(conjunto, nombre, residente, reside=True, tipo=TipoVinculo.ARRENDATARIO):
    with usar_conjunto(conjunto.id):
        unidad = Unidad.objects.create(nombre=nombre)
        VinculoUnidad.objects.create(persona=residente, unidad=unidad, tipo=tipo, reside=reside)
    return unidad


@pytest.fixture
def torres():
    return Conjunto.objects.create(nombre="Torres del Río")


@pytest.fixture
def vigilante():
    return persona("Vigilante", "900000001")


@pytest.fixture
def gimnasio(torres):
    return crear_area(torres)


@pytest.fixture
def pedro(torres):
    residente = persona("Pedro", "1000000001")
    return residente, vivienda(torres, "Torre 1 – 101", residente)


@pytest.fixture
def lucia(torres):
    residente = persona("Lucía", "1000000002")
    return residente, vivienda(torres, "Torre 1 – 102", residente)


@pytest.fixture
def ana(torres):
    residente = persona("Ana", "1000000003")
    return residente, vivienda(torres, "Torre 1 – 103", residente)


def entrar(torres, vigilante, area, vecino, acompanantes=0, ahora=AHORA):
    residente, unidad = vecino
    with usar_conjunto(torres.id):
        return servicios.registrar(vigilante, area.id, residente.id, unidad.id, acompanantes, ahora=ahora)


def motivos_de(torres, vigilante, area, vecino, acompanantes=0, ahora=AHORA):
    with pytest.raises(servicios.IncumpleReglas) as error:
        entrar(torres, vigilante, area, vecino, acompanantes, ahora)
    return error.value.motivos


def ocupacion(torres, area):
    with usar_conjunto(torres.id):
        return servicios.ocupacion(area)


def definir(torres, vigilante, tipo, parametros, area=None):
    with usar_conjunto(torres.id):
        return reglas.crear(vigilante, tipo, parametros, AHORA.date(), area.id if area else None)


def ingresos_de(torres):
    with usar_conjunto(torres.id):
        return list(Ingreso.objects.order_by("entrada_en"))


# El recorrido


def test_entra_un_residente_y_la_ocupacion_sube_en_uno_mas_sus_acompanantes(torres, vigilante, gimnasio, pedro, lucia):
    ingreso = entrar(torres, vigilante, gimnasio, pedro, acompanantes=1)
    entrar(torres, vigilante, gimnasio, lucia)

    assert (ingreso.estado, ingreso.acompanantes, ingreso.registrado_por_id) == (
        EstadoIngreso.ADENTRO,
        1,
        vigilante.id,
    )
    assert ocupacion(torres, gimnasio) == 3
    assert {resultado["tipo"] for resultado in ingreso.evaluacion} >= {"RESIDE", "AFORO"}
    with usar_conjunto(torres.id):
        assert Registro.objects.filter(accion="ingreso.registrar", entidad_id=ingreso.id).count() == 1


def test_con_el_aforo_lleno_no_entra_y_el_motivo_lo_dice(torres, vigilante, gimnasio, pedro, lucia, ana):
    entrar(torres, vigilante, gimnasio, pedro, acompanantes=2)

    motivos = motivos_de(torres, vigilante, gimnasio, lucia)

    assert len(motivos) == 1 and "quedan 0 puestos libres de 3" in motivos[0]
    assert len(ingresos_de(torres)) == 1


def test_con_un_cupo_no_entra_quien_llega_con_un_acompanante(torres, vigilante, gimnasio, pedro, lucia):
    entrar(torres, vigilante, gimnasio, pedro, acompanantes=1)

    motivos = motivos_de(torres, vigilante, gimnasio, lucia, acompanantes=1)

    assert "Entran 2 y en esta zona quedan 1 puestos libres de 3" in motivos[0]


def test_un_rechazo_no_deja_fila(torres, vigilante, gimnasio, pedro):
    entrar(torres, vigilante, gimnasio, pedro, acompanantes=1)
    motivos_de(torres, vigilante, gimnasio, pedro)

    assert len(ingresos_de(torres)) == 1


@pytest.mark.parametrize(
    ("ajuste", "texto"),
    [
        ({"en_mantenimiento": True}, "no está disponible"),
        ({"activo": False}, "no está disponible"),
        ({"hora_apertura": time(11), "hora_cierre": time(22)}, "La zona atiende de 11:00 a 22:00"),
    ],
)
def test_fuera_de_horario_o_en_mantenimiento_no_entra(torres, vigilante, pedro, ajuste, texto):
    area = crear_area(torres, **ajuste)

    motivos = motivos_de(torres, vigilante, area, pedro)

    assert any(texto in motivo for motivo in motivos)


def test_en_un_dia_que_no_abre_no_entra(torres, vigilante, gimnasio, pedro):
    renglones = [{"dia_semana": AHORA.weekday(), "motivo": "Limpieza profunda"}]
    definir(torres, vigilante, "DIAS_QUE_NO_ABRE", {"renglones": renglones}, gimnasio)

    motivos = motivos_de(torres, vigilante, gimnasio, pedro)

    assert motivos == ["Esta zona no abre hoy: Limpieza profunda."]


def test_un_area_con_reserva_no_admite_ingresos(torres, vigilante, pedro):
    salon = crear_area(torres, "Salón", modo_uso="reserva", duracion_franja_minutos=240, permanencia_maxima_minutos=None)

    with pytest.raises(servicios.AreaSinIngreso):
        entrar(torres, vigilante, salon, pedro)


def test_con_dos_motivos_a_la_vez_llegan_los_dos(torres, vigilante, pedro):
    area = crear_area(torres, en_mantenimiento=True, aforo_maximo=1)

    motivos = motivos_de(torres, vigilante, area, pedro, acompanantes=2)

    assert len(motivos) == 2
    assert any("no está disponible" in motivo for motivo in motivos)
    assert any("Entran 3" in motivo for motivo in motivos)


def test_quien_no_reside_en_esa_vivienda_no_entra(torres, vigilante, gimnasio, pedro, lucia):
    pedro_persona, _ = pedro
    _, unidad_de_lucia = lucia

    motivos = motivos_de(torres, vigilante, gimnasio, (pedro_persona, unidad_de_lucia))

    assert motivos == ["La persona no vive en la vivienda elegida."]


def test_un_propietario_que_no_vive_ahi_no_entra(torres, vigilante, gimnasio):
    dueno = persona("Dueño", "1000000009")
    unidad = vivienda(torres, "Torre 2 – 201", dueno, reside=False, tipo=TipoVinculo.PROPIETARIO)

    with pytest.raises(servicios.ResidenteNoEncontrado):
        entrar(torres, vigilante, gimnasio, (dueno, unidad))


def test_quien_ya_esta_adentro_de_otra_zona_no_entra(torres, vigilante, gimnasio, pedro):
    piscina = crear_area(torres, "Piscina")
    entrar(torres, vigilante, gimnasio, pedro)

    assert motivos_de(torres, vigilante, piscina, pedro) == ["La persona ya está adentro de una zona."]


def test_la_base_rechaza_un_segundo_ingreso_abierto_aunque_se_salte_el_servicio(torres, vigilante, gimnasio, pedro):
    residente, unidad = pedro
    entrar(torres, vigilante, gimnasio, pedro)

    with usar_conjunto(torres.id), pytest.raises(IntegrityError), transaction.atomic():
        Ingreso.objects.create(
            area=gimnasio,
            persona=residente,
            unidad=unidad,
            entrada_en=AHORA,
            salida_prevista_en=AHORA + timedelta(hours=1),
            registrado_por=vigilante,
        )


# Acompañantes


def test_se_respeta_el_maximo_de_acompanantes_por_vivienda_sumando_los_que_ya_tiene_adentro(
    torres, vigilante, pedro
):
    definir(torres, vigilante, "ACOMPANANTES", {"maximo": 2})
    area = crear_area(torres, aforo_maximo=20)
    residente, unidad = pedro
    otro = persona("Hermana", "1000000004")
    with usar_conjunto(torres.id):
        VinculoUnidad.objects.create(persona=otro, unidad=unidad, tipo=TipoVinculo.PROPIETARIO, reside=True)

    entrar(torres, vigilante, area, pedro, acompanantes=1)
    motivos = motivos_de(torres, vigilante, area, (otro, unidad), acompanantes=2)
    entrar(torres, vigilante, area, (otro, unidad), acompanantes=1)

    assert "ya tiene 1 acompañantes adentro y el máximo es 2" in motivos[0]
    assert ocupacion(torres, area) == 4


def test_con_maximo_cero_no_entra_ningun_acompanante_pero_si_la_persona_sola(torres, vigilante, gimnasio, pedro, lucia):
    definir(torres, vigilante, "ACOMPANANTES", {"maximo": 0})

    motivos = motivos_de(torres, vigilante, gimnasio, pedro, acompanantes=1)
    entrar(torres, vigilante, gimnasio, lucia)

    assert motivos == ["En este conjunto no se permiten acompañantes."]


def test_sin_regla_de_acompanantes_entran_con_el_aforo_como_unico_tope(torres, vigilante, gimnasio, pedro):
    ingreso = entrar(torres, vigilante, gimnasio, pedro, acompanantes=2)

    assert ingreso.acompanantes == 2


# La salida prevista y el tiempo


def test_la_salida_prevista_es_la_entrada_mas_la_permanencia(torres, vigilante, gimnasio, pedro):
    ingreso = entrar(torres, vigilante, gimnasio, pedro)

    assert ingreso.salida_prevista_en == AHORA + timedelta(minutes=60)


def test_la_salida_prevista_no_pasa_del_cierre(torres, vigilante, pedro):
    area = crear_area(torres, permanencia_maxima_minutos=240, hora_cierre=time(11))

    ingreso = entrar(torres, vigilante, area, pedro)

    assert timezone.localtime(ingreso.salida_prevista_en).time() == time(11)


def test_al_cumplirse_el_tiempo_el_ingreso_queda_vencido_el_cupo_se_libera_y_avisa_una_sola_vez(
    torres, vigilante, gimnasio, pedro
):
    residente, _ = pedro
    ingreso = entrar(torres, vigilante, gimnasio, pedro, acompanantes=1)
    despues = AHORA + timedelta(minutes=61)

    with usar_conjunto(torres.id):
        zonas = servicios.zonas(ahora=despues)
        servicios.zonas(ahora=despues + timedelta(minutes=5))
        guardado = Ingreso.objects.get(pk=ingreso.id)
        avisos = list(Notificacion.objects.filter(origen="ingreso", referencia=ingreso.id))

    assert (guardado.estado, guardado.salida_en) == (EstadoIngreso.VENCIDO, ingreso.salida_prevista_en)
    assert (zonas[0]["adentro"], zonas[0]["cupos"]) == (0, 3)
    assert [aviso.persona_id for aviso in avisos] == [residente.id]


def test_quien_se_vencio_puede_volver_a_entrar_si_hay_cupo(torres, vigilante, gimnasio, pedro):
    entrar(torres, vigilante, gimnasio, pedro)

    de_nuevo = entrar(torres, vigilante, gimnasio, pedro, ahora=AHORA + timedelta(minutes=90))

    assert de_nuevo.estado == EstadoIngreso.ADENTRO
    assert [i.estado for i in ingresos_de(torres)] == [EstadoIngreso.VENCIDO, EstadoIngreso.ADENTRO]


def test_registrar_libera_a_los_vencidos_aunque_el_registro_sea_rechazado(torres, vigilante, pedro, lucia):
    area = crear_area(torres, aforo_maximo=1)
    entrar(torres, vigilante, area, pedro)

    motivos_de(torres, vigilante, area, lucia, acompanantes=1, ahora=AHORA + timedelta(minutes=90))

    assert [i.estado for i in ingresos_de(torres)] == [EstadoIngreso.VENCIDO]


def test_un_ingreso_abierto_conserva_su_salida_aunque_cambie_la_permanencia_del_area(
    torres, vigilante, gimnasio, pedro
):
    ingreso = entrar(torres, vigilante, gimnasio, pedro)
    with usar_conjunto(torres.id):
        Area.objects.filter(pk=gimnasio.id).update(permanencia_maxima_minutos=15)
        servicios.zonas(ahora=AHORA + timedelta(minutes=30))
        guardado = Ingreso.objects.get(pk=ingreso.id)

    assert guardado.estado == EstadoIngreso.ADENTRO
    assert guardado.salida_prevista_en == AHORA + timedelta(minutes=60)


# La salida manual


def test_la_salida_manual_libera_el_cupo_y_repetirla_responde_ya_salio(torres, vigilante, gimnasio, pedro):
    ingreso = entrar(torres, vigilante, gimnasio, pedro, acompanantes=1)

    with usar_conjunto(torres.id):
        salido = servicios.registrar_salida(vigilante, ingreso.id, ahora=AHORA + timedelta(minutes=20))
        with pytest.raises(servicios.YaSalio):
            servicios.registrar_salida(vigilante, ingreso.id, ahora=AHORA + timedelta(minutes=21))
        auditados = Registro.objects.filter(accion="ingreso.salida").count()

    assert (salido.estado, salido.salida_registrada_por_id) == (EstadoIngreso.SALIO, vigilante.id)
    assert ocupacion(torres, gimnasio) == 0
    assert auditados == 1


def test_una_salida_inexistente_responde_no_encontrado(torres, vigilante):
    with usar_conjunto(torres.id), pytest.raises(servicios.IngresoNoEncontrado):
        servicios.registrar_salida(vigilante, "00000000-0000-0000-0000-000000000000")


# Las listas


def test_las_listas_separan_a_quien_esta_adentro_de_quien_se_vencio_hoy(torres, vigilante, gimnasio, pedro, lucia):
    entrar(torres, vigilante, gimnasio, pedro)
    entrar(torres, vigilante, gimnasio, lucia, ahora=AHORA + timedelta(minutes=50))
    despues = AHORA + timedelta(minutes=65)

    with usar_conjunto(torres.id):
        dentro = [i.persona.nombres for i in servicios.adentro(ahora=despues)]
        vencidos = [i.persona.nombres for i in servicios.vencidos_de_hoy(ahora=despues)]
        historial = [i.persona.nombres for i in servicios.historial(ahora=despues)]
        de_otra_zona = list(servicios.historial(area_id=crear_area(torres, "Piscina").id, ahora=despues))

    assert (dentro, vencidos, historial) == (["Lucía"], ["Pedro"], ["Lucía", "Pedro"])
    assert de_otra_zona == []


def test_las_zonas_traen_solo_conteos_y_dicen_si_estan_abiertas(torres, vigilante, gimnasio, pedro):
    crear_area(torres, "Salón", modo_uso="reserva", duracion_franja_minutos=240, permanencia_maxima_minutos=None)
    entrar(torres, vigilante, gimnasio, pedro, acompanantes=1)

    with usar_conjunto(torres.id):
        zonas = servicios.zonas(ahora=AHORA)
        de_noche = servicios.zonas(ahora=AHORA.replace(hour=23))

    assert len(zonas) == 1
    assert (zonas[0]["adentro"], zonas[0]["cupos"], zonas[0]["abierta_ahora"]) == (2, 1, True)
    assert de_noche[0]["abierta_ahora"] is False and "05:00 a 22:00" in de_noche[0]["motivo_cierre"]


# La búsqueda del residente


def test_la_busqueda_encuentra_con_puntos_y_espacios_y_no_trae_otros_datos(torres, vigilante, pedro):
    with usar_conjunto(torres.id):
        encontrados = servicios.buscar_residente(vigilante, " 1.000.000.001 ")
        auditoria = Registro.objects.get(accion="ingreso.buscar_residente")

    assert [(e["persona"].nombres, [u.nombre for u in e["unidades"]]) for e in encontrados] == [
        ("Pedro", ["Torre 1 – 101"])
    ]
    assert auditoria.detalle == {"encontrados": 1}
    assert "1000000001" not in str(auditoria.__dict__)


def test_la_busqueda_no_encuentra_a_quien_solo_es_de_otro_conjunto_ni_a_un_propietario_que_no_vive_ahi(
    torres, vigilante
):
    miradores = Conjunto.objects.create(nombre="Miradores")
    forastero = persona("Forastero", "1000000050")
    vivienda(miradores, "Casa 1", forastero)
    dueno = persona("Dueño", "1000000051")
    vivienda(torres, "Torre 2 – 201", dueno, reside=False, tipo=TipoVinculo.PROPIETARIO)

    with usar_conjunto(torres.id):
        assert servicios.buscar_residente(vigilante, "1000000050") == []
        assert servicios.buscar_residente(vigilante, "1000000051") == []


def test_dos_personas_con_el_mismo_numero_llegan_las_dos(torres, vigilante):
    adulto = persona("Adulto", "1000000060", TipoDocumento.CC)
    menor = persona("Menor", "1000000060", TipoDocumento.TI)
    vivienda(torres, "Torre 3 – 301", adulto)
    vivienda(torres, "Torre 3 – 302", menor)

    with usar_conjunto(torres.id):
        encontrados = servicios.buscar_residente(vigilante, "1000000060")

    assert sorted(e["persona"].nombres for e in encontrados) == ["Adulto", "Menor"]


# Lo que hace cumplir la base


def test_la_base_rechaza_un_ingreso_que_apunta_a_un_area_o_a_una_vivienda_de_otro_conjunto(
    torres, vigilante, gimnasio, pedro
):
    miradores = Conjunto.objects.create(nombre="Miradores")
    area_ajena = crear_area(miradores)
    residente, unidad = pedro
    vecina = persona("Vecina", "1000000070")
    unidad_ajena = vivienda(miradores, "Casa 1", vecina)

    for area, vivienda_elegida in ((area_ajena, unidad), (gimnasio, unidad_ajena)):
        with usar_conjunto(torres.id), pytest.raises(IntegrityError), transaction.atomic():
            Ingreso.objects.create(
                area=area,
                persona=residente,
                unidad=vivienda_elegida,
                entrada_en=AHORA,
                salida_prevista_en=AHORA + timedelta(hours=1),
                registrado_por=vigilante,
            )


def test_la_base_rechaza_una_salida_antes_de_la_entrada_y_una_salida_que_no_corresponde_al_estado(
    torres, vigilante, gimnasio, pedro
):
    residente, unidad = pedro
    incoherentes = [
        {"salida_prevista_en": AHORA},
        {"estado": EstadoIngreso.ADENTRO, "salida_en": AHORA + timedelta(minutes=5)},
        {"estado": EstadoIngreso.SALIO, "salida_en": None},
    ]
    for ajuste in incoherentes:
        datos = {"entrada_en": AHORA, "salida_prevista_en": AHORA + timedelta(hours=1), **ajuste}
        with usar_conjunto(torres.id), pytest.raises(IntegrityError), transaction.atomic():
            Ingreso.objects.create(
                area=gimnasio, persona=residente, unidad=unidad, registrado_por=vigilante, **datos
            )


# Permisos


def test_los_permisos_de_ingreso_son_de_vigilancia_y_de_administracion_y_el_historial_es_sensible():
    assert "ingreso.registrar" in PERMISOS_POR_ROL[Rol.VIGILANCIA]
    assert "ingreso.ver_historico" not in PERMISOS_POR_ROL[Rol.VIGILANCIA]
    assert "ingreso.ver_historico" in PERMISOS_POR_ROL[Rol.ADMINISTRACION]
    assert "ingreso.registrar" not in PERMISOS_POR_ROL[Rol.ADMINISTRACION]
    assert {"ingreso.registrar", "ingreso.ver_historico"} <= PERMISOS_POR_ROL[Rol.SUPERUSUARIO]
    assert "ingreso.ver_historico" in PERMISOS_SENSIBLES and "ingreso.registrar" not in PERMISOS_SENSIBLES
    for rol in (Rol.RESIDENTE, Rol.SECRETARIA):
        assert not {"ingreso.registrar", "ingreso.ver_historico"} & PERMISOS_POR_ROL[rol]


# La API (plan de zonas con ingreso, F4). Las peticiones usan la hora real: la zona abre todo el día.

CONTRASENA = "una-clave-larga-2026"


def cliente_de(conjunto, rol, correo, residente=None):
    """Una sesión con ese rol. Si se pasa `residente`, la cuenta es de esa persona."""
    quien = residente or persona(rol.label, str(2000000000 + Persona.objects.count()))
    Asignacion.objects.get_or_create(persona=quien, rol=rol, conjunto=conjunto)
    Usuario.objects.create_user(correo, CONTRASENA, quien)
    cliente = APIClient()
    respuesta = cliente.post("/auth/login/", {"correo": correo, "contrasena": CONTRASENA}, format="json")
    cliente.credentials(HTTP_AUTHORIZATION=f"Token {respuesta.json()['token']}")
    TokenDeSesion.objects.filter(usuario__correo=correo).update(dos_factores_verificado=True)
    return cliente


@pytest.fixture
def abierto(torres):
    return crear_area(torres, "Gimnasio 24 h", hora_apertura=time(0), hora_cierre=time(23, 59, 59), permanencia_maxima_minutos=30)


@pytest.fixture
def portero(torres):
    return cliente_de(torres, Rol.VIGILANCIA, "portero@torres.com")


@pytest.fixture
def administracion(torres):
    return cliente_de(torres, Rol.ADMINISTRACION, "admin@torres.com")


@pytest.fixture
def secretaria(torres):
    return cliente_de(torres, Rol.SECRETARIA, "secretaria@torres.com")


@pytest.fixture
def vecino_pedro(torres, pedro):
    return cliente_de(torres, Rol.RESIDENTE, "pedro@torres.com", residente=pedro[0])


def registrar_por_api(cliente, area, vecino, acompanantes=0):
    residente, unidad = vecino
    return cliente.post(
        "/ingresos/",
        {"area": str(area.id), "persona": str(residente.id), "unidad": str(unidad.id), "acompanantes": acompanantes},
        format="json",
    )


def test_vigilancia_busca_registra_ve_quien_esta_adentro_y_registra_la_salida(portero, torres, abierto, pedro):
    busqueda = portero.post("/ingresos/residentes/buscar/", {"numero_documento": "1.000.000.001"}, format="json")
    registro = registrar_por_api(portero, abierto, pedro, acompanantes=1)
    dentro = portero.get("/ingresos/").json()
    salida = portero.post(f"/ingresos/{registro.json()['id']}/salida/")

    assert busqueda.status_code == 200
    assert busqueda.json() == [
        {
            "persona": str(pedro[0].id),
            "nombre": "Pedro Gómez",
            "unidades": [{"id": str(pedro[1].id), "nombre": "Torre 1 – 101"}],
        }
    ]
    assert registro.status_code == 201
    assert (registro.json()["estado"], registro.json()["acompanantes"]) == ("ADENTRO", 1)
    assert [i["persona"]["nombre"] for i in dentro["adentro"]] == ["Pedro Gómez"]
    assert dentro["vencidos_hoy"] == [] and "historial" not in dentro
    assert (salida.status_code, salida.json()["estado"]) == (200, "SALIO")
    assert portero.post(f"/ingresos/{registro.json()['id']}/salida/").status_code == 409


def test_buscar_un_documento_que_no_es_del_conjunto_responde_no_encontrado(portero, torres):
    forastero = persona("Forastero", "1000000050")
    vivienda(Conjunto.objects.create(nombre="Miradores"), "Casa 1", forastero)

    ajeno = portero.post("/ingresos/residentes/buscar/", {"numero_documento": "1000000050"}, format="json")
    inexistente = portero.post("/ingresos/residentes/buscar/", {"numero_documento": "9999999"}, format="json")

    assert ajeno.status_code == inexistente.status_code == 404
    assert ajeno.json() == inexistente.json()


def test_un_residente_y_secretaria_ven_los_cupos_y_no_pueden_buscar_registrar_ni_listar(
    vecino_pedro, secretaria, abierto, pedro
):
    for cliente in (vecino_pedro, secretaria):
        assert cliente.get("/ingresos/zonas/").status_code == 200
        assert cliente.post("/ingresos/residentes/buscar/", {"numero_documento": "1"}, format="json").status_code == 403
        assert registrar_por_api(cliente, abierto, pedro).status_code == 403
        assert cliente.get("/ingresos/").status_code == 403
        assert cliente.post("/ingresos/00000000-0000-0000-0000-000000000000/salida/").status_code == 403


def test_los_cupos_son_un_conteo_sin_nombres(portero, vecino_pedro, abierto, pedro):
    registrar_por_api(portero, abierto, pedro, acompanantes=1)

    zonas = vecino_pedro.get("/ingresos/zonas/")

    assert zonas.status_code == 200
    assert [(z["area"]["nombre"], z["adentro"], z["cupos"], z["abierta_ahora"]) for z in zonas.json()] == [
        ("Gimnasio 24 h", 2, 1, True)
    ]
    assert "Pedro" not in zonas.content.decode() and "Gómez" not in zonas.content.decode()


def test_administracion_ve_los_cupos_y_el_historial_con_filtros_y_no_puede_registrar(
    administracion, portero, torres, abierto, pedro
):
    piscina = crear_area(torres, "Piscina")
    registrar_por_api(portero, abierto, pedro)

    historial = administracion.get("/ingresos/").json()
    de_la_piscina = administracion.get("/ingresos/", {"area": str(piscina.id)}).json()
    de_ayer = administracion.get("/ingresos/", {"fecha": str(timezone.localdate() - timedelta(days=1))}).json()

    assert administracion.get("/ingresos/zonas/").status_code == 200
    assert set(historial) == {"historial"}
    assert [i["area"]["nombre"] for i in historial["historial"]] == ["Gimnasio 24 h"]
    assert de_la_piscina["historial"] == [] and de_ayer["historial"] == []
    assert registrar_por_api(administracion, abierto, pedro).status_code == 403
    assert (
        administracion.post("/ingresos/residentes/buscar/", {"numero_documento": "1"}, format="json").status_code == 403
    )


def test_un_registro_que_no_cumple_responde_400_con_todos_los_motivos_y_no_deja_fila(portero, torres, pedro):
    area = crear_area(torres, "Piscina", en_mantenimiento=True, aforo_maximo=1)

    respuesta = registrar_por_api(portero, area, pedro, acompanantes=2)

    assert respuesta.status_code == 400
    assert len(respuesta.json()["motivos"]) == 2
    assert ingresos_de(torres) == []


def test_un_area_con_reserva_responde_409_y_el_area_la_persona_o_la_vivienda_ajenas_responden_404(
    portero, torres, abierto, pedro
):
    salon = crear_area(torres, "Salón", modo_uso="reserva", duracion_franja_minutos=240, permanencia_maxima_minutos=None)
    miradores = Conjunto.objects.create(nombre="Miradores")
    forastero = persona("Forastero", "1000000050")
    casa = vivienda(miradores, "Casa 1", forastero)
    area_ajena = crear_area(miradores, "Piscina")

    assert registrar_por_api(portero, salon, pedro).status_code == 409
    assert registrar_por_api(portero, area_ajena, pedro).status_code == 404
    assert registrar_por_api(portero, abierto, (forastero, casa)).status_code == 404
    assert registrar_por_api(portero, abierto, (pedro[0], casa)).status_code == 404
    assert ingresos_de(torres) == []


def test_conjunto_en_el_cuerpo_se_rechaza(portero, torres, abierto, pedro):
    residente, unidad = pedro

    registro = portero.post(
        "/ingresos/",
        {"area": str(abierto.id), "persona": str(residente.id), "unidad": str(unidad.id), "conjunto": str(torres.id)},
        format="json",
    )

    assert registro.status_code == 400
    assert ingresos_de(torres) == []
