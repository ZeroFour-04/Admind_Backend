"""Pruebas de HU-09: catálogo de áreas comunes del conjunto activo."""
from datetime import date, time, timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APIClient

from apps.areas.models import Area
from apps.areas.servicios import franjas_del_dia
from apps.auditoria.models import Registro
from apps.comun.aislamiento.contexto import usar_conjunto
from apps.conjuntos.models import Conjunto
from apps.conjuntos.servicios import requisitos_para_operar
from apps.cuentas.models import TokenDeSesion, Usuario
from apps.ingresos.models import EstadoIngreso, Ingreso
from apps.permisos.catalogo import Rol
from apps.permisos.models import Asignacion
from apps.personas.models import Persona, TipoDocumento
from apps.reglas import servicios as reglas
from apps.reglas.catalogo import TipoDeRegla
from apps.reglas.models import Regla
from apps.reservas.models import EstadoSolicitud, Solicitud
from apps.unidades.models import Unidad

pytestmark = pytest.mark.django_db

CONTRASENA = "una-clave-larga-2026"
SALON = {
    "nombre": "Salón comunal",
    "hora_apertura": "08:00",
    "hora_cierre": "22:00",
    "duracion_franja_minutos": 240,
    "aforo_maximo": 50,
}


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


def areas_de(conjunto):
    with usar_conjunto(conjunto.id):
        return list(Area.objects.order_by("nombre"))


@pytest.fixture
def torres():
    return Conjunto.objects.create(nombre="Torres del Río", direccion="Calle 9 # 4-50")


@pytest.fixture
def admin(torres):
    crear_usuario("admin@torres.com", Rol.ADMINISTRACION, torres)
    return cliente_para("admin@torres.com")


@pytest.fixture
def residente(torres):
    crear_usuario("vecino@torres.com", Rol.RESIDENTE, torres)
    return cliente_para("vecino@torres.com")


@pytest.fixture
def salon(admin):
    return admin.post("/areas/", SALON, format="json").json()


# Criterios de aceptación


def test_sin_area_gestionar_no_se_crea_ni_se_edita_y_solo_se_ven_las_activas(admin, residente, salon):
    otra = admin.post("/areas/", {**SALON, "nombre": "BBQ"}, format="json").json()
    admin.post(f"/areas/{otra['id']}/desactivar/")

    assert residente.post("/areas/", {**SALON, "nombre": "Gimnasio"}, format="json").status_code == 403
    assert residente.patch(f"/areas/{salon['id']}/", {"nombre": "Otro"}, format="json").status_code == 403
    assert residente.post(f"/areas/{salon['id']}/desactivar/").status_code == 403
    listado = residente.get("/areas/")
    assert listado.status_code == 200
    assert [area["nombre"] for area in listado.json()] == ["Salón comunal"]
    assert residente.get(f"/areas/{otra['id']}/").status_code == 404
    assert [area["nombre"] for area in admin.get("/areas/").json()] == ["BBQ", "Salón comunal"]


def test_un_area_retirada_se_desactiva_y_no_se_borra(admin, torres, salon):
    respuesta = admin.post(f"/areas/{salon['id']}/desactivar/")

    assert respuesta.status_code == 200
    assert respuesta.json()["activo"] is False
    assert [(area.nombre, area.activo) for area in areas_de(torres)] == [("Salón comunal", False)]
    assert admin.delete(f"/areas/{salon['id']}/").status_code == 405
    assert admin.post(f"/areas/{salon['id']}/desactivar/").status_code == 409


def test_un_area_se_pone_en_mantenimiento_y_sigue_en_el_catalogo(admin, residente, salon):
    respuesta = admin.patch(f"/areas/{salon['id']}/", {"en_mantenimiento": True}, format="json")

    assert respuesta.json()["en_mantenimiento"] is True
    assert residente.get(f"/areas/{salon['id']}/").json()["en_mantenimiento"] is True


# Reglas del catálogo


def test_editar_cambia_nombre_y_horario_y_deja_auditoria(admin, torres, salon):
    respuesta = admin.patch(
        f"/areas/{salon['id']}/", {"nombre": "Salón social", "hora_cierre": "20:00"}, format="json"
    )

    assert respuesta.status_code == 200
    assert (respuesta.json()["nombre"], respuesta.json()["hora_cierre"]) == ("Salón social", "20:00")
    with usar_conjunto(torres.id):
        registro = Registro.objects.get(accion="area.editar")
    assert registro.antes == {"nombre": "Salón comunal", "hora_cierre": "22:00:00"}
    assert registro.despues == {"nombre": "Salón social", "hora_cierre": "20:00:00"}


def test_las_condiciones_de_alquiler_se_guardan_y_se_incluyen_en_el_area(admin, torres, salon):
    condiciones = "No se permiten fiestas después de las 10 p. m."
    respuesta = admin.patch(
        f"/areas/{salon['id']}/",
        {"condiciones_alquiler": condiciones},
        format="json",
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["condiciones_alquiler"] == condiciones
    with usar_conjunto(torres.id):
        registro = Registro.objects.get(accion="area.editar")
    assert registro.despues == {"condiciones_alquiler": condiciones}


def test_crear_y_desactivar_quedan_en_la_auditoria(admin, torres, salon):
    admin.post(f"/areas/{salon['id']}/desactivar/")

    with usar_conjunto(torres.id):
        acciones = sorted(Registro.objects.values_list("accion", flat=True))
    assert acciones == ["area.crear", "area.desactivar"]


def test_el_cierre_debe_ser_posterior_a_la_apertura(admin, salon):
    assert "hora_cierre" in admin.post("/areas/", {**SALON, "nombre": "BBQ", "hora_cierre": "08:00"}, format="json").json()
    assert admin.patch(f"/areas/{salon['id']}/", {"hora_apertura": "23:00"}, format="json").status_code == 400


def test_la_duracion_minima_de_una_franja_es_de_dos_horas(admin, salon):
    crear_minima = admin.post(
        "/areas/", {**SALON, "nombre": "BBQ", "duracion_franja_minutos": 120}, format="json"
    )
    crear = admin.post(
        "/areas/", {**SALON, "nombre": "Gimnasio", "duracion_franja_minutos": 119}, format="json"
    )
    editar = admin.patch(
        f"/areas/{salon['id']}/", {"duracion_franja_minutos": 119}, format="json"
    )

    assert crear_minima.status_code == 201
    assert crear.status_code == 400
    assert editar.status_code == 400
    assert "duracion_franja_minutos" in crear.json()
    assert "duracion_franja_minutos" in editar.json()


def test_el_aforo_es_obligatorio_y_minimo_uno(admin, salon):
    sin_aforo = {campo: valor for campo, valor in SALON.items() if campo != "aforo_maximo"}
    crear_sin = admin.post("/areas/", {**sin_aforo, "nombre": "BBQ"}, format="json")
    crear_cero = admin.post("/areas/", {**SALON, "nombre": "Gimnasio", "aforo_maximo": 0}, format="json")
    editar = admin.patch(f"/areas/{salon['id']}/", {"aforo_maximo": 80}, format="json")

    assert crear_sin.status_code == 400 and "aforo_maximo" in crear_sin.json()
    assert crear_cero.status_code == 400 and "aforo_maximo" in crear_cero.json()
    assert (editar.status_code, editar.json()["aforo_maximo"]) == (200, 80)


def test_la_base_no_acepta_un_area_con_aforo_cero(torres):
    with usar_conjunto(torres.id), pytest.raises(IntegrityError), transaction.atomic():
        Area.objects.create(
            nombre="BBQ", hora_apertura=time(8), hora_cierre=time(22), duracion_franja_minutos=120, aforo_maximo=0
        )


def test_nombre_repetido_en_el_mismo_conjunto_responde_400(admin, salon):
    respuesta = admin.post("/areas/", SALON, format="json")

    assert respuesta.status_code == 400
    assert respuesta.json()["nombre"] == ["Ya existe un área con este nombre en el conjunto."]


def test_las_franjas_son_bloques_consecutivos_desde_la_apertura_sin_pasar_el_cierre(torres):
    with usar_conjunto(torres.id):
        area = Area.objects.create(
            nombre="BBQ", hora_apertura=time(8), hora_cierre=time(21), duracion_franja_minutos=240, aforo_maximo=50
        )

    assert franjas_del_dia(area, date(2026, 12, 26)) == [
        (time(8), time(12)),
        (time(12), time(16)),
        (time(16), time(20)),
    ]


def test_con_un_area_activa_se_cumple_el_requisito_de_areas_para_operar(admin, torres, salon):
    def requisito_de_areas():
        with usar_conjunto(torres.id):
            return next(r for r in requisitos_para_operar(torres) if r.clave == "areas").cumplido

    assert requisito_de_areas() is True
    admin.post(f"/areas/{salon['id']}/desactivar/")
    assert requisito_de_areas() is False


# Modo de uso (plan de zonas con ingreso, F1)

GIMNASIO = {
    "nombre": "Gimnasio",
    "modo_uso": "ingreso",
    "hora_apertura": "05:00",
    "hora_cierre": "22:00",
    "permanencia_maxima_minutos": 60,
    "aforo_maximo": 3,
}


def test_un_area_sin_modo_sigue_siendo_con_reserva(admin, salon):
    assert (salon["modo_uso"], salon["duracion_franja_minutos"], salon["permanencia_maxima_minutos"]) == (
        "reserva",
        240,
        None,
    )


def test_se_crea_un_area_con_ingreso_con_permanencia_y_sin_duracion(admin, torres):
    respuesta = admin.post("/areas/", GIMNASIO, format="json")

    assert respuesta.status_code == 201
    assert (
        respuesta.json()["modo_uso"],
        respuesta.json()["duracion_franja_minutos"],
        respuesta.json()["permanencia_maxima_minutos"],
    ) == ("ingreso", None, 60)
    assert franjas_del_dia(areas_de(torres)[0], date(2026, 12, 26)) == []


def test_cada_modo_pide_sus_campos_y_rechaza_los_del_otro(admin):
    sin_permanencia = {campo: v for campo, v in GIMNASIO.items() if campo != "permanencia_maxima_minutos"}
    ingreso_sin = admin.post("/areas/", sin_permanencia, format="json")
    ingreso_con_duracion = admin.post("/areas/", {**GIMNASIO, "duracion_franja_minutos": 120}, format="json")
    ingreso_corta = admin.post("/areas/", {**GIMNASIO, "permanencia_maxima_minutos": 10}, format="json")
    reserva_con_permanencia = admin.post("/areas/", {**SALON, "permanencia_maxima_minutos": 60}, format="json")
    reserva_sin_duracion = admin.post(
        "/areas/", {k: v for k, v in SALON.items() if k != "duracion_franja_minutos"}, format="json"
    )

    assert "permanencia_maxima_minutos" in ingreso_sin.json()
    assert "duracion_franja_minutos" in ingreso_con_duracion.json()
    assert "permanencia_maxima_minutos" in ingreso_corta.json()
    assert "permanencia_maxima_minutos" in reserva_con_permanencia.json()
    assert "duracion_franja_minutos" in reserva_sin_duracion.json()
    assert {r.status_code for r in (ingreso_sin, ingreso_con_duracion, ingreso_corta)} == {400}


def test_la_base_rechaza_un_area_incoherente_con_su_modo(torres):
    base = {"hora_apertura": time(8), "hora_cierre": time(22), "aforo_maximo": 5}
    incoherentes = [
        {"modo_uso": "ingreso", "duracion_franja_minutos": None, "permanencia_maxima_minutos": None},
        {"modo_uso": "ingreso", "duracion_franja_minutos": 120, "permanencia_maxima_minutos": 60},
        {"modo_uso": "reserva", "duracion_franja_minutos": None, "permanencia_maxima_minutos": None},
        {"modo_uso": "reserva", "duracion_franja_minutos": 120, "permanencia_maxima_minutos": 60},
    ]
    for numero, datos in enumerate(incoherentes):
        with usar_conjunto(torres.id), pytest.raises(IntegrityError), transaction.atomic():
            Area.objects.create(nombre=f"Zona {numero}", **base, **datos)


def test_cada_modo_edita_solo_lo_suyo(admin, torres, salon):
    gimnasio = admin.post("/areas/", GIMNASIO, format="json").json()

    permanencia = admin.patch(f"/areas/{gimnasio['id']}/", {"permanencia_maxima_minutos": 90}, format="json")
    duracion_en_ingreso = admin.patch(f"/areas/{gimnasio['id']}/", {"duracion_franja_minutos": 120}, format="json")
    permanencia_en_reserva = admin.patch(f"/areas/{salon['id']}/", {"permanencia_maxima_minutos": 90}, format="json")
    mismo_modo = admin.patch(f"/areas/{gimnasio['id']}/", {"modo_uso": "ingreso"}, format="json")

    assert (permanencia.status_code, permanencia.json()["permanencia_maxima_minutos"]) == (200, 90)
    assert permanencia.json()["cambio_de_modo"] is None
    assert duracion_en_ingreso.status_code == 400
    assert permanencia_en_reserva.status_code == 400
    assert (mismo_modo.status_code, mismo_modo.json()["cambio_de_modo"]) == (200, None)
    assert {a.nombre: a.modo_uso for a in areas_de(torres)} == {"Gimnasio": "ingreso", "Salón comunal": "reserva"}


# Cambiar el modo de uso de un área que ya existe (2026-10-13)


def test_el_modo_se_cambia_con_el_dato_del_modo_nuevo_y_queda_en_la_auditoria(admin, torres):
    gimnasio = admin.post("/areas/", GIMNASIO, format="json").json()

    respuesta = admin.patch(
        f"/areas/{gimnasio['id']}/", {"modo_uso": "reserva", "duracion_franja_minutos": 120}, format="json"
    )

    assert respuesta.status_code == 200
    assert (
        respuesta.json()["modo_uso"],
        respuesta.json()["duracion_franja_minutos"],
        respuesta.json()["permanencia_maxima_minutos"],
    ) == ("reserva", 120, None)
    assert respuesta.json()["cambio_de_modo"] == {
        "reservas_por_cumplir": 0,
        "personas_adentro": 0,
        "reglas_retiradas": [],
    }
    assert len(franjas_del_dia(areas_de(torres)[0], date(2026, 12, 26))) == 8
    with usar_conjunto(torres.id):
        registro = Registro.objects.get(accion="area.cambiar_modo")
    assert (registro.antes["modo_uso"], registro.despues["modo_uso"]) == ("ingreso", "reserva")
    assert (registro.antes["permanencia_maxima_minutos"], registro.despues["permanencia_maxima_minutos"]) == (60, None)


def test_cambiar_el_modo_exige_el_dato_del_modo_nuevo_y_rechaza_el_del_anterior(admin, torres, salon):
    sin_permanencia = admin.patch(f"/areas/{salon['id']}/", {"modo_uso": "ingreso"}, format="json")
    con_duracion = admin.patch(
        f"/areas/{salon['id']}/",
        {"modo_uso": "ingreso", "permanencia_maxima_minutos": 60, "duracion_franja_minutos": 240},
        format="json",
    )
    modo_inventado = admin.patch(f"/areas/{salon['id']}/", {"modo_uso": "libre"}, format="json")

    assert sin_permanencia.status_code == 400 and "permanencia_maxima_minutos" in sin_permanencia.json()
    assert con_duracion.status_code == 400 and "duracion_franja_minutos" in con_duracion.json()
    assert modo_inventado.status_code == 400 and "modo_uso" in modo_inventado.json()
    assert [(a.modo_uso, a.duracion_franja_minutos) for a in areas_de(torres)] == [("reserva", 240)]


def test_pasar_a_ingreso_retira_las_reglas_de_reserva_y_cuenta_las_reservas_que_quedan(admin, torres, salon):
    autor = Persona.objects.get(usuario__correo="admin@torres.com")
    manana = timezone.localdate() + timedelta(days=1)
    with usar_conjunto(torres.id):
        area = Area.objects.get()
        reglas.crear(autor, TipoDeRegla.CUPO_POR_UNIDAD, {"reservas": 2, "dias": 30}, manana, area.id)
        reglas.crear(autor, TipoDeRegla.UNA_RESERVA_POR_DIA, {}, manana, area.id)
        cierre = [{"dia_semana": 0, "motivo": "Limpieza"}]
        reglas.crear(autor, TipoDeRegla.DIAS_QUE_NO_ABRE, {"renglones": cierre}, manana, area.id)
        unidad = Unidad.objects.create(nombre="Torre 1 – 101")
        franja = {"hora_inicio": time(8), "hora_fin": time(12), "bloqueo_vence_en": timezone.now()}
        apartada = Solicitud.objects.create(
            area=area, persona=autor, unidad=unidad, fecha=manana, estado=EstadoSolicitud.APARTADA, **franja
        )
        # Ni la de ayer ni la rechazada cuentan: ya no ocupan nada.
        Solicitud.objects.create(
            area=area,
            persona=autor,
            unidad=unidad,
            fecha=manana - timedelta(days=2),
            estado=EstadoSolicitud.RESERVADA,
            **franja,
        )
        Solicitud.objects.create(
            area=area,
            persona=autor,
            unidad=unidad,
            fecha=manana,
            estado=EstadoSolicitud.RECHAZADA,
            categoria_rechazo="OTRO",
            **franja,
        )

    respuesta = admin.patch(
        f"/areas/{salon['id']}/", {"modo_uso": "ingreso", "permanencia_maxima_minutos": 90}, format="json"
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["cambio_de_modo"] == {
        "reservas_por_cumplir": 1,
        "personas_adentro": 0,
        "reglas_retiradas": ["Límite de reservas por apartamento", "Una reserva al día"],
    }
    with usar_conjunto(torres.id):
        assert [regla.tipo for regla in Regla.objects.abiertas()] == [TipoDeRegla.DIAS_QUE_NO_ABRE]
        assert Registro.objects.filter(accion="regla.retirar").count() == 2
        apartada.refresh_from_db()
    assert apartada.estado == EstadoSolicitud.APARTADA


def test_pasar_a_reserva_cuenta_a_quien_sigue_adentro_y_no_le_da_salida(admin, torres):
    gimnasio = admin.post("/areas/", GIMNASIO, format="json").json()
    autor = Persona.objects.get(usuario__correo="admin@torres.com")
    ahora = timezone.now()
    with usar_conjunto(torres.id):
        ingreso = Ingreso.objects.create(
            area_id=gimnasio["id"],
            persona=autor,
            unidad=Unidad.objects.create(nombre="Torre 1 – 101"),
            acompanantes=1,
            entrada_en=ahora,
            salida_prevista_en=ahora + timedelta(hours=1),
            registrado_por=autor,
        )

    respuesta = admin.patch(
        f"/areas/{gimnasio['id']}/", {"modo_uso": "reserva", "duracion_franja_minutos": 120}, format="json"
    )

    assert respuesta.json()["cambio_de_modo"]["personas_adentro"] == 2
    with usar_conjunto(torres.id):
        ingreso.refresh_from_db()
    assert ingreso.estado == EstadoIngreso.ADENTRO
