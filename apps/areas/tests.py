"""Pruebas de HU-09: catálogo de áreas comunes del conjunto activo."""
from datetime import date, time

import pytest
from rest_framework.test import APIClient

from apps.areas.models import Area
from apps.areas.servicios import franjas_del_dia
from apps.auditoria.models import Registro
from apps.comun.aislamiento.contexto import usar_conjunto
from apps.conjuntos.models import Conjunto
from apps.conjuntos.servicios import requisitos_para_operar
from apps.cuentas.models import TokenDeSesion, Usuario
from apps.permisos.catalogo import Rol
from apps.permisos.models import Asignacion
from apps.personas.models import Persona, TipoDocumento

pytestmark = pytest.mark.django_db

CONTRASENA = "una-clave-larga-2026"
SALON = {
    "nombre": "Salón comunal",
    "hora_apertura": "08:00",
    "hora_cierre": "22:00",
    "duracion_franja_minutos": 240,
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


def test_crear_y_desactivar_quedan_en_la_auditoria(admin, torres, salon):
    admin.post(f"/areas/{salon['id']}/desactivar/")

    with usar_conjunto(torres.id):
        acciones = sorted(Registro.objects.values_list("accion", flat=True))
    assert acciones == ["area.crear", "area.desactivar"]


def test_el_cierre_debe_ser_posterior_a_la_apertura(admin, salon):
    assert "hora_cierre" in admin.post("/areas/", {**SALON, "nombre": "BBQ", "hora_cierre": "08:00"}, format="json").json()
    assert admin.patch(f"/areas/{salon['id']}/", {"hora_apertura": "23:00"}, format="json").status_code == 400


def test_nombre_repetido_en_el_mismo_conjunto_responde_400(admin, salon):
    respuesta = admin.post("/areas/", SALON, format="json")

    assert respuesta.status_code == 400
    assert respuesta.json()["nombre"] == ["Ya existe un área con este nombre en el conjunto."]


def test_las_franjas_son_bloques_consecutivos_desde_la_apertura_sin_pasar_el_cierre(torres):
    with usar_conjunto(torres.id):
        area = Area.objects.create(
            nombre="BBQ", hora_apertura=time(8), hora_cierre=time(21), duracion_franja_minutos=240
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
