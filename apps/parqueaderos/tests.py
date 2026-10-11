"""Pruebas de HU-28: el catálogo de parqueaderos del conjunto activo.

La ocupación por una visita se prueba en `apps/visitantes/test_visitantes.py`.
"""
import pytest
from django.db import IntegrityError, transaction
from django.urls import URLResolver, get_resolver
from rest_framework.test import APIClient

from apps.auditoria.models import Registro
from apps.comun.aislamiento.contexto import usar_conjunto
from apps.conjuntos.models import Conjunto
from apps.cuentas.models import TokenDeSesion, Usuario
from apps.parqueaderos.models import Parqueadero
from apps.permisos.catalogo import Rol
from apps.permisos.models import Asignacion
from apps.personas.models import Persona, TipoDocumento
from apps.unidades.models import Unidad

pytestmark = pytest.mark.django_db

CONTRASENA = "una-clave-larga-2026"


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
def administracion(torres):
    crear_usuario("admin@torres.com", Rol.ADMINISTRACION, torres)
    return cliente_para("admin@torres.com")


@pytest.fixture
def vigilancia(torres):
    crear_usuario("vigilante@torres.com", Rol.VIGILANCIA, torres)
    return cliente_para("vigilante@torres.com")


@pytest.fixture
def residente(torres):
    crear_usuario("vecino@torres.com", Rol.RESIDENTE, torres)
    return cliente_para("vecino@torres.com")


def crear(cliente, codigo="V-01", tipo="visitantes", **extra):
    return cliente.post("/parqueaderos/", {"codigo": codigo, "tipo": tipo, **extra}, format="json")


# Administración crea, lista y retira


def test_administracion_crea_un_parqueadero_y_lo_lista_con_su_contrato(administracion, torres):
    respuesta = crear(administracion, "V-01", accesible=True, notas="Junto a la portería")

    assert respuesta.status_code == 201
    creado = respuesta.json()
    assert {k: creado[k] for k in ("codigo", "tipo", "accesible", "notas", "ocupado")} == {
        "codigo": "V-01",
        "tipo": "visitantes",
        "accesible": True,
        "notas": "Junto a la portería",
        "ocupado": False,
    }
    assert administracion.get("/parqueaderos/").json() == [creado]


def test_el_codigo_se_guarda_en_mayusculas_y_sin_espacios(administracion):
    respuesta = crear(administracion, "  v-02 ")

    assert respuesta.json()["codigo"] == "V-02"


def test_el_codigo_no_se_repite_ni_sin_distinguir_mayusculas(administracion, torres):
    assert crear(administracion, "V-01").status_code == 201

    repetido = crear(administracion, "v-01", tipo="residentes")

    assert repetido.status_code == 400
    assert repetido.json() == {"codigo": ["Ya existe un parqueadero con ese código en el conjunto."]}
    with usar_conjunto(torres.id):
        assert Parqueadero.objects.count() == 1


def test_la_base_tambien_rechaza_el_codigo_repetido_escribiendo_directo(torres):
    persona = crear_usuario("admin@torres.com", Rol.ADMINISTRACION, torres)
    with usar_conjunto(torres.id):
        Parqueadero.objects.create(codigo="V-01", tipo="visitantes", creado_por=persona)

        with pytest.raises(IntegrityError), transaction.atomic():
            Parqueadero.objects.create(codigo="v-01", tipo="residentes", creado_por=persona)


def test_el_mismo_codigo_puede_existir_en_otro_conjunto(administracion, torres):
    otro = Conjunto.objects.create(nombre="Mirador")
    creador = crear_usuario("otro@mirador.com", Rol.ADMINISTRACION, otro)
    with usar_conjunto(otro.id):
        Parqueadero.objects.create(codigo="V-01", tipo="visitantes", creado_por=creador)

    assert crear(administracion, "V-01").status_code == 201


def test_se_crean_los_dos_tipos_y_el_listado_filtra_por_tipo(administracion):
    crear(administracion, "V-01", "visitantes")
    crear(administracion, "R-01", "residentes")

    todos = administracion.get("/parqueaderos/").json()
    visitantes = administracion.get("/parqueaderos/", {"tipo": "visitantes"}).json()

    assert [p["codigo"] for p in todos] == ["R-01", "V-01"]
    assert [p["codigo"] for p in visitantes] == ["V-01"]
    assert administracion.get("/parqueaderos/", {"tipo": "carros"}).status_code == 400


def test_un_tipo_que_no_existe_o_un_codigo_vacio_se_rechazan(administracion):
    assert crear(administracion, "V-01", tipo="motos").status_code == 400
    assert crear(administracion, "   ").status_code == 400


def test_retirar_un_parqueadero_lo_saca_del_listado_y_queda_en_la_auditoria(administracion, torres):
    creado = crear(administracion, "V-01").json()
    crear(administracion, "V-02")

    respuesta = administracion.post(f"/parqueaderos/{creado['id']}/desactivar/")

    assert respuesta.status_code == 200
    assert [p["codigo"] for p in administracion.get("/parqueaderos/").json()] == ["V-02"]
    with usar_conjunto(torres.id):
        registro = Registro.objects.get(accion="parqueadero.desactivar", entidad_id=creado["id"])
        assert Parqueadero.objects.get(pk=creado["id"]).activo is False
        assert Registro.objects.filter(accion="parqueadero.crear").count() == 2
    assert registro.antes == {"activo": True}
    assert registro.despues == {"activo": False, "codigo": "V-01"}
    # Ya retirado, no está: no se retira dos veces.
    assert administracion.post(f"/parqueaderos/{creado['id']}/desactivar/").status_code == 404


def test_un_codigo_retirado_sigue_ocupando_el_codigo(administracion):
    creado = crear(administracion, "V-01").json()
    administracion.post(f"/parqueaderos/{creado['id']}/desactivar/")

    assert crear(administracion, "V-01").status_code == 400


# Quién puede qué


def test_vigilancia_lista_los_parqueaderos_y_no_los_crea(administracion, vigilancia):
    creado = crear(administracion, "V-01").json()

    listado = vigilancia.get("/parqueaderos/", {"tipo": "visitantes", "libres": "1"})
    creacion = crear(vigilancia, "V-09")
    retiro = vigilancia.post(f"/parqueaderos/{creado['id']}/desactivar/")

    assert listado.status_code == 200 and [p["codigo"] for p in listado.json()] == ["V-01"]
    assert creacion.status_code == 403
    assert retiro.status_code == 403


def test_un_residente_no_ve_ni_crea_ni_retira(administracion, residente):
    creado = crear(administracion, "V-01").json()

    assert residente.get("/parqueaderos/").status_code == 403
    assert crear(residente, "V-09").status_code == 403
    assert residente.post(f"/parqueaderos/{creado['id']}/desactivar/").status_code == 403


def test_el_permiso_nuevo_es_de_administracion_y_no_es_sensible():
    from apps.permisos.catalogo import PERMISOS, PERMISOS_POR_ROL, PERMISOS_SENSIBLES

    assert "parqueadero.gestionar" in PERMISOS
    assert "parqueadero.gestionar" in PERMISOS_POR_ROL[Rol.ADMINISTRACION]
    assert "parqueadero.gestionar" not in PERMISOS_SENSIBLES
    for rol in (Rol.SECRETARIA, Rol.VIGILANCIA, Rol.RESIDENTE):
        assert "parqueadero.gestionar" not in PERMISOS_POR_ROL[rol]


# Criterio 4: asignar un parqueadero a una unidad no existe


def rutas_de_parqueaderos(patrones):
    for patron in patrones:
        if isinstance(patron, URLResolver):
            yield from rutas_de_parqueaderos(patron.url_patterns)
        elif str(patron.callback.__module__).startswith("apps.parqueaderos"):
            yield str(patron.pattern), patron.name


def test_ninguna_ruta_asigna_un_parqueadero_a_una_unidad():
    rutas = list(rutas_de_parqueaderos(get_resolver().url_patterns))

    assert rutas, "no se encontraron las rutas de parqueaderos"
    assert not [ruta for ruta in rutas if "asignar" in ruta[0] or "asignar" in (ruta[1] or "")]
    assert not [ruta for ruta in rutas if "unidad" in ruta[0]]


def test_el_modelo_no_tiene_relacion_con_unidades_y_la_api_ignora_una_unidad(administracion, torres):
    with usar_conjunto(torres.id):
        unidad = Unidad.objects.create(nombre="Torre 1 – 101")
    campos_hacia_unidad = [
        campo for campo in Parqueadero._meta.get_fields() if getattr(campo.related_model, "__name__", "") == "Unidad"
    ]
    assert campos_hacia_unidad == []

    respuesta = crear(administracion, "V-01", unidad=str(unidad.id))

    assert respuesta.status_code == 201
    assert "unidad" not in respuesta.json()
