"""Pruebas del modelo Conjunto y del asistente de creación (HU-03, HU-26)."""
import uuid
from datetime import time

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APIClient

from apps.areas.models import Area
from apps.comun.aislamiento.contexto import usar_conjunto
from apps.conjuntos.models import Conjunto
from apps.cuentas.models import TokenDeSesion, Usuario
from apps.documentos.models import Reglamento
from apps.permisos.catalogo import Rol
from apps.permisos.models import Asignacion
from apps.personas.models import Persona, TipoDocumento
from apps.reglas.catalogo import TipoDeRegla
from apps.reglas.models import Regla
from apps.unidades.models import Unidad

pytestmark = pytest.mark.django_db

CONTRASENA = "una-clave-larga-2026"


def test_conjunto_nuevo_nace_activo_y_no_operativo():
    conjunto = Conjunto.objects.create(nombre="Torres del Río")
    conjunto.refresh_from_db()

    assert conjunto.activo is True
    assert conjunto.operativo is False


def test_conjunto_se_identifica_por_uuid():
    conjunto = Conjunto.objects.create(nombre="Torres del Río")

    assert isinstance(conjunto.pk, uuid.UUID)


def test_conjunto_nace_con_el_acento_verde_y_la_base_rechaza_uno_fuera_del_catalogo():
    assert Conjunto.objects.create(nombre="Torres del Río").acento == "verde"
    with pytest.raises(IntegrityError):
        Conjunto.objects.create(nombre="Mirador", acento="fucsia")


def test_la_base_exige_el_color_con_el_personalizado_y_lo_rechaza_con_los_del_catalogo():
    Conjunto.objects.create(nombre="Torres del Río", acento="personalizado", color_personalizado="#1a8fe3")
    for datos in (
        {"acento": "personalizado"},
        {"acento": "personalizado", "color_personalizado": "#1A8FE3"},
        {"acento": "vino", "color_personalizado": "#1a8fe3"},
    ):
        with pytest.raises(IntegrityError), transaction.atomic():
            Conjunto.objects.create(nombre="Mirador", **datos)


# Asistente por la API


def crear_persona(correo, *roles):
    persona = Persona.objects.create(
        tipo_documento=TipoDocumento.CC,
        numero_documento=str(Persona.objects.count() + 1023456789),
        nombres="Laura",
        apellidos="Gómez",
    )
    for rol, conjunto in roles:
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
    return Conjunto.objects.create(nombre="Torres del Río", direccion="Calle 1")


@pytest.fixture
def admin_torres(torres):
    return crear_persona("admin@torres.com", (Rol.ADMINISTRACION, torres))


@pytest.fixture
def admin(admin_torres):
    return cliente_para("admin@torres.com")


@pytest.fixture
def superusuario():
    crear_persona("super@admind.com", (Rol.SUPERUSUARIO, None))
    return cliente_para("super@admind.com")


def crear(cliente, **datos):
    return cliente.post("/conjuntos/", {"nombre": "Mirador", "direccion": "Carrera 2", **datos}, format="json")


def test_administracion_crea_un_conjunto_y_queda_como_su_administracion(admin, admin_torres):
    respuesta = crear(admin, acento="vino")

    assert respuesta.status_code == 201
    nuevo = Conjunto.objects.get(nombre="Mirador")
    assert nuevo.acento == "vino"
    assert nuevo.operativo is False
    assert Asignacion.objects.filter(persona=admin_torres, rol=Rol.ADMINISTRACION, conjunto=nuevo).exists()


def test_al_crear_el_conjunto_nuevo_pasa_a_ser_el_activo(admin):
    respuesta = crear(admin)

    nuevo = Conjunto.objects.get(nombre="Mirador")
    assert respuesta.json()["conjunto_activo"]["id"] == str(nuevo.id)
    assert TokenDeSesion.objects.get().conjunto_activo_id == nuevo.id


def test_superusuario_crea_sin_conjunto_activo_y_no_queda_como_administracion(superusuario):
    respuesta = crear(superusuario)

    assert respuesta.status_code == 201
    nuevo = Conjunto.objects.get(nombre="Mirador")
    assert not Asignacion.objects.filter(conjunto=nuevo).exists()
    assert TokenDeSesion.objects.get().conjunto_activo_id == nuevo.id


def test_sin_el_permiso_conjunto_crear_recibe_403(torres):
    crear_persona("vecino@torres.com", (Rol.RESIDENTE, torres))
    residente = cliente_para("vecino@torres.com")

    assert crear(residente).status_code == 403
    assert not Conjunto.objects.filter(nombre="Mirador").exists()


def test_administracion_sin_conjunto_activo_puede_crear(torres):
    otro = Conjunto.objects.create(nombre="Balcones")
    persona = crear_persona("admin@dos.com", (Rol.ADMINISTRACION, torres), (Rol.ADMINISTRACION, otro))
    # Con dos conjuntos entra sin conjunto activo: crear no depende de estar dentro de uno.
    cliente = cliente_para("admin@dos.com")
    assert TokenDeSesion.objects.get().conjunto_activo_id is None

    respuesta = crear(cliente)

    assert respuesta.status_code == 201
    nuevo = Conjunto.objects.get(nombre="Mirador")
    assert Asignacion.objects.filter(persona=persona, rol=Rol.ADMINISTRACION, conjunto=nuevo).exists()
    assert TokenDeSesion.objects.get().conjunto_activo_id == nuevo.id


def test_el_ingreso_avisa_si_puede_crear_conjuntos_aunque_no_haya_conjunto_activo(torres):
    otro = Conjunto.objects.create(nombre="Balcones")
    crear_persona("admin@dos.com", (Rol.ADMINISTRACION, torres), (Rol.ADMINISTRACION, otro))
    crear_persona("vecino@dos.com", (Rol.RESIDENTE, torres), (Rol.RESIDENTE, otro))

    admin_dos = APIClient().post("/auth/login/", {"correo": "admin@dos.com", "contrasena": CONTRASENA}, format="json")
    vecino_dos = APIClient().post("/auth/login/", {"correo": "vecino@dos.com", "contrasena": CONTRASENA}, format="json")

    assert admin_dos.json()["conjunto_activo"] is None
    assert admin_dos.json()["permisos"] == []
    assert admin_dos.json()["puede_crear_conjunto"] is True
    assert vecino_dos.json()["puede_crear_conjunto"] is False


def test_residente_sin_conjunto_activo_sigue_sin_poder_crear(torres):
    otro = Conjunto.objects.create(nombre="Balcones")
    crear_persona("vecino@dos.com", (Rol.RESIDENTE, torres), (Rol.RESIDENTE, otro))
    cliente = cliente_para("vecino@dos.com")

    assert crear(cliente).status_code == 403
    assert not Conjunto.objects.filter(nombre="Mirador").exists()


def test_el_asistente_crea_el_conjunto_con_un_color_propio(admin):
    respuesta = crear(admin, acento="personalizado", color="#7a3cc2")

    assert respuesta.status_code == 201
    assert respuesta.json()["conjunto"]["color"] == "#7a3cc2"
    assert Conjunto.objects.get(nombre="Mirador").color_personalizado == "#7a3cc2"


def test_nombre_repetido_o_acento_fuera_del_catalogo_responden_400(admin):
    assert crear(admin, nombre="torres del río").status_code == 400
    assert crear(admin, acento="fucsia").status_code == 400


def test_el_nombre_del_conjunto_admite_30_caracteres_y_con_31_responde_400(admin):
    assert crear(admin, nombre="C" * 31).status_code == 400
    assert not Conjunto.objects.filter(nombre="C" * 31).exists()

    respuesta = crear(admin, nombre="C" * 30)

    assert respuesta.status_code == 201
    assert Conjunto.objects.filter(nombre="C" * 30).exists()


def test_administracion_solo_ve_sus_conjuntos_y_el_superusuario_todos(admin, torres):
    Conjunto.objects.create(nombre="Ajeno")

    assert [c["nombre"] for c in admin.get("/auth/conjuntos/").json()] == ["Torres del Río"]
    crear_persona("super@admind.com", (Rol.SUPERUSUARIO, None))
    superusuario = cliente_para("super@admind.com")

    assert [c["nombre"] for c in superusuario.get("/auth/conjuntos/").json()] == ["Ajeno", "Torres del Río"]


def test_superusuario_ve_todos_los_conjuntos_creados_incluidos_los_inactivos(admin, torres):
    Conjunto.objects.create(nombre="Inactivo", activo=False)
    crear_persona("super@admind.com", (Rol.SUPERUSUARIO, None))
    superusuario = cliente_para("super@admind.com")

    assert [c["nombre"] for c in superusuario.get("/auth/conjuntos/").json()] == ["Inactivo", "Torres del Río"]


def test_superusuario_puede_dar_de_baja_un_conjunto_sin_confirmacion(superusuario, torres):
    superusuario.post("/auth/conjunto-activo/", {"conjunto": str(torres.id)}, format="json")

    respuesta = superusuario.delete("/conjuntos/actual/", format="json")

    assert respuesta.status_code == 204
    torres.refresh_from_db()
    assert torres.activo is False
    assert torres.operativo is False


def test_el_listado_de_conjuntos_trae_el_acento(admin, torres):
    torres.acento = "azul"
    torres.save()

    assert admin.get("/auth/conjuntos/").json()[0]["acento"] == "azul"


# Resumen, edición y activación del conjunto activo


def test_resumen_muestra_datos_administradores_y_requisitos(admin):
    resumen = admin.get("/conjuntos/actual/").json()

    assert resumen["conjunto"]["nombre"] == "Torres del Río"
    assert [a["nombre"] for a in resumen["administradores"]] == ["Laura Gómez"]
    requisitos = {r["clave"]: r for r in resumen["requisitos"]}
    assert requisitos["datos_basicos"]["cumplido"] is True
    assert requisitos["administracion"]["cumplido"] is True
    assert requisitos["areas"] == {
        "clave": "areas",
        "descripcion": "Catálogo de áreas comunes",
        "cumplido": False,
        "disponible": True,
    }


def test_guardado_parcial_se_editan_los_datos_del_conjunto_activo(admin, torres):
    respuesta = admin.patch("/conjuntos/actual/", {"direccion": "Calle 9 # 4-50", "acento": "ocre"}, format="json")

    assert respuesta.status_code == 200
    torres.refresh_from_db()
    assert (torres.direccion, torres.acento) == ("Calle 9 # 4-50", "ocre")


def test_residente_no_edita_ni_ve_el_resumen(torres):
    crear_persona("vecino@torres.com", (Rol.RESIDENTE, torres))
    residente = cliente_para("vecino@torres.com")

    assert residente.get("/conjuntos/actual/").status_code == 403
    assert residente.patch("/conjuntos/actual/", {"nombre": "Otro"}, format="json").status_code == 403


def test_conjunto_incompleto_no_queda_operativo(superusuario, torres):
    superusuario.post("/auth/conjunto-activo/", {"conjunto": str(torres.id)}, format="json")

    respuesta = superusuario.post("/conjuntos/actual/activar/")

    assert respuesta.status_code == 400
    assert "Catálogo de áreas comunes" in respuesta.json()["faltantes"]
    torres.refresh_from_db()
    assert torres.operativo is False


def test_sin_viviendas_el_conjunto_no_queda_operativo(superusuario, torres):
    superusuario.post("/auth/conjunto-activo/", {"conjunto": str(torres.id)}, format="json")

    respuesta = superusuario.post("/conjuntos/actual/activar/")

    assert respuesta.status_code == 400
    assert "Al menos una vivienda registrada" in respuesta.json()["faltantes"]


def test_sin_administracion_la_activacion_lo_dice_explicitamente(superusuario):
    crear(superusuario)

    respuesta = superusuario.post("/conjuntos/actual/activar/")

    assert respuesta.status_code == 400
    assert "Al menos una persona con rol Administración" in respuesta.json()["faltantes"]


def test_administracion_tambien_activa_su_conjunto_y_un_residente_no(admin, torres):
    """Desde el 2026-10-06 `conjunto.activar` también es de Administración (plan del asistente, D1 b)."""
    crear_persona("vecino@torres.com", (Rol.RESIDENTE, torres))

    assert admin.get("/conjuntos/actual/").json()["puede_activar"] is True
    # Pasa el permiso y se detiene en los requisitos: 400 con lo que falta, no 403.
    assert admin.post("/conjuntos/actual/activar/").status_code == 400
    assert cliente_para("vecino@torres.com").post("/conjuntos/actual/activar/").status_code == 403


def completar(conjunto, persona, con_reglamento=True, con_reglas_del_conjunto=True):
    """Lo que el asistente deja guardado paso a paso, creado aquí de una vez."""
    with usar_conjunto(conjunto.id):
        Unidad.objects.create(nombre="Torre 1 – Apto 101")
        salon = Area.objects.create(
            nombre="Salón comunal",
            hora_apertura=time(8),
            hora_cierre=time(22),
            duracion_franja_minutos=240,
            aforo_maximo=50,
        )
        Regla.objects.create(
            area=salon, tipo=TipoDeRegla.CUPO_POR_UNIDAD, parametros={"reservas": 2, "dias": 30}, creada_por=persona
        )
        if con_reglas_del_conjunto:
            Regla.objects.create(tipo=TipoDeRegla.ANTICIPACION_MAXIMA, parametros={"dias": 30}, creada_por=persona)
        if con_reglamento:
            Reglamento.objects.create(
                contenido=b"%PDF-1.7 prueba", nombre="reglamento.pdf", peso=15, huella="a" * 64, subido_por=persona
            )


def test_sin_reglamento_el_conjunto_no_queda_operativo(superusuario, torres, admin_torres):
    completar(torres, admin_torres, con_reglamento=False)
    superusuario.post("/auth/conjunto-activo/", {"conjunto": str(torres.id)}, format="json")

    respuesta = superusuario.post("/conjuntos/actual/activar/")

    assert respuesta.status_code == 400
    assert respuesta.json()["faltantes"] == ["Reglamento cargado"]


def test_el_limite_de_un_area_no_cuenta_como_reglas_del_conjunto(superusuario, torres, admin_torres):
    completar(torres, admin_torres, con_reglas_del_conjunto=False)
    superusuario.post("/auth/conjunto-activo/", {"conjunto": str(torres.id)}, format="json")

    respuesta = superusuario.post("/conjuntos/actual/activar/")

    assert respuesta.status_code == 400
    assert respuesta.json()["faltantes"] == ["Reglas del conjunto definidas"]
    torres.refresh_from_db()
    assert torres.operativo is False


def test_al_definir_la_anticipacion_maxima_el_requisito_de_reglas_queda_cumplido(admin, torres, admin_torres):
    completar(torres, admin_torres, con_reglas_del_conjunto=False)

    def reglas_del_conjunto():
        requisitos = admin.get("/conjuntos/actual/").json()["requisitos"]
        return next(requisito for requisito in requisitos if requisito["clave"] == "reglas_del_conjunto")["cumplido"]

    assert reglas_del_conjunto() is False
    regla = {"tipo": "ANTICIPACION_MAXIMA", "parametros": {"dias": 30}, "vigencia_desde": str(timezone.localdate())}
    assert admin.post("/reglas/", regla, format="json").status_code == 201
    assert reglas_del_conjunto() is True
    assert admin.post("/conjuntos/actual/activar/").status_code == 200


def test_un_conjunto_completo_queda_operativo(superusuario, torres, admin_torres):
    completar(torres, admin_torres)
    superusuario.post("/auth/conjunto-activo/", {"conjunto": str(torres.id)}, format="json")

    respuesta = superusuario.post("/conjuntos/actual/activar/")

    assert respuesta.status_code == 200
    assert respuesta.json()["conjunto"]["operativo"] is True
    torres.refresh_from_db()
    assert torres.operativo is True


def test_superusuario_configura_el_conjunto_que_crea(superusuario):
    crear(superusuario)

    assert superusuario.get("/conjuntos/actual/").json()["puede_activar"] is True
    respuesta = superusuario.patch("/conjuntos/actual/", {"acento": "pizarra"}, format="json")

    assert respuesta.status_code == 200
    assert Conjunto.objects.get(nombre="Mirador").acento == "pizarra"


def test_superusuario_asigna_el_primer_administrador_en_el_paso_2(superusuario):
    crear(superusuario)

    respuesta = superusuario.post(
        "/auth/usuarios/",
        {
            "tipo_documento": TipoDocumento.CC,
            "numero_documento": "70000001",
            "nombres": "Andrés",
            "apellidos": "Rojas",
            "correo": "andres@mirador.com",
            "contrasena": CONTRASENA,
            "rol": Rol.ADMINISTRACION,
        },
        format="json",
    )

    assert respuesta.status_code == 201
    requisitos = {r["clave"]: r for r in superusuario.get("/conjuntos/actual/").json()["requisitos"]}
    assert requisitos["administracion"]["cumplido"] is True
