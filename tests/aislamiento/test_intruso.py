"""Prueba del intruso por endpoint y prueba transversal de rutas (maestro §5.4, HU-05, HU-26)."""
import pytest
from django.urls import URLResolver, get_resolver, reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.views import APIView

from apps.comun.aislamiento.contexto import usar_conjunto
from apps.comun.aislamiento.vistas import VistaDeConjunto
from apps.conjuntos.models import Conjunto
from apps.cuentas.models import TokenDeSesion, Usuario
from apps.permisos.catalogo import Rol
from apps.permisos.models import Asignacion
from apps.personas.models import Persona, TipoDocumento
from tests.aislamiento.models import Area

pytestmark = pytest.mark.django_db

CONTRASENA = "una-clave-larga-2026"


def crear_usuario(correo, *roles):
    persona = Persona.objects.create(
        tipo_documento=TipoDocumento.CC,
        numero_documento=str(Persona.objects.count() + 1023456789),
        nombres="Laura",
        apellidos="Gómez",
    )
    for rol, conjunto in roles:
        Asignacion.objects.create(persona=persona, rol=rol, conjunto=conjunto)
    return Usuario.objects.create_user(correo, CONTRASENA, persona)


def cliente_para(correo):
    """Sesión con el segundo factor dado por verificado: su flujo se prueba en cuentas (HU-02)."""
    cliente = APIClient()
    respuesta = cliente.post("/auth/login/", {"correo": correo, "contrasena": CONTRASENA}, format="json")
    cliente.credentials(HTTP_AUTHORIZATION=f"Token {respuesta.json()['token']}")
    TokenDeSesion.objects.filter(usuario__correo=correo).update(dos_factores_verificado=True)
    return cliente


def crear_area(conjunto, nombre):
    with usar_conjunto(conjunto.id):
        return Area.objects.create(nombre=nombre)


@pytest.fixture
def torres():
    return Conjunto.objects.create(nombre="Torres del Río")


@pytest.fixture
def mirador():
    return Conjunto.objects.create(nombre="Mirador")


@pytest.fixture
def intruso(torres):
    """Administración en Torres del Río y nada en Mirador. Con un solo conjunto, entra directo."""
    crear_usuario("admin@torres.com", (Rol.ADMINISTRACION, torres))
    return cliente_para("admin@torres.com")


# Registro de la prueba del intruso. Toda ruta con datos de un conjunto se agrega aquí;
# si no, falla test_toda_ruta_de_la_api_esta_cubierta.


def detalle_de_area(otro_conjunto):
    return reverse("pruebas-area-detalle", kwargs={"pk": crear_area(otro_conjunto, "Piscina").pk})


def listado_de_areas(otro_conjunto):
    return reverse("pruebas-areas"), str(crear_area(otro_conjunto, "Piscina").pk)


def usuario_de(otro_conjunto):
    correo = f"vecino{Usuario.objects.count()}@otro.com"
    return crear_usuario(correo, (Rol.RESIDENTE, otro_conjunto))


def detalle_de_usuario(otro_conjunto):
    return reverse("usuario-detalle", kwargs={"usuario_id": usuario_de(otro_conjunto).pk})


def listado_de_usuarios(otro_conjunto):
    return reverse("usuarios"), str(usuario_de(otro_conjunto).pk)


def resumen_del_conjunto(otro_conjunto):
    return reverse("conjunto-actual"), str(otro_conjunto.pk)


def activar_conjunto(otro_conjunto):
    def intacto():
        return not Conjunto.objects.get(pk=otro_conjunto.pk).operativo

    return "post", reverse("conjunto-activar"), intacto


DETALLES = {"pruebas-area-detalle": detalle_de_area, "usuario-detalle": detalle_de_usuario}
LISTADOS = {
    "pruebas-areas": listado_de_areas,
    "usuarios": listado_de_usuarios,
    "conjunto-actual": resumen_del_conjunto,
}
# Rutas de conjunto sin identificador ni listado: actúan sobre el conjunto activo.
ACCIONES = {"conjunto-activar": activar_conjunto}
RUTAS_SIN_CONJUNTO = {
    "iniciar-sesion",
    "cerrar-sesion",
    "conjuntos-disponibles",
    "conjunto-activo",
    # El Superusuario crea conjuntos sin tener uno activo (HU-03).
    "conjunto-crear",
    "recuperar-contrasena",
    "restablecer-contrasena",
    "dos-factores-configurar",
    "dos-factores-activar",
    "dos-factores-verificar",
}


@pytest.mark.parametrize("ruta", sorted(DETALLES))
def test_intruso_pide_por_id_un_recurso_de_otro_conjunto_y_recibe_404(ruta, intruso, mirador):
    url = DETALLES[ruta](mirador)

    assert intruso.get(url).status_code == 404


@pytest.mark.parametrize("ruta", sorted(LISTADOS))
def test_listado_no_trae_datos_de_otro_conjunto(ruta, intruso, mirador):
    url, id_ajeno = LISTADOS[ruta](mirador)

    respuesta = intruso.get(url)

    assert respuesta.status_code == 200
    assert id_ajeno not in respuesta.content.decode()


@pytest.mark.parametrize("ruta", sorted(ACCIONES))
def test_accion_no_acepta_otro_conjunto_y_no_lo_toca(ruta, intruso, mirador):
    metodo, url, intacto = ACCIONES[ruta](mirador)

    respuesta = getattr(intruso, metodo)(url, {"conjunto": str(mirador.id)}, format="json")

    assert respuesta.status_code == 400
    assert intacto()


def test_conjunto_en_la_url_se_rechaza(intruso, mirador):
    respuesta = intruso.get(reverse("pruebas-areas"), {"conjunto_id": str(mirador.id)})

    assert respuesta.status_code == 400


def test_conjunto_en_el_cuerpo_se_rechaza(intruso, mirador):
    respuesta = intruso.post(
        reverse("pruebas-areas"), {"nombre": "Piscina", "conjunto": str(mirador.id)}, format="json"
    )

    assert respuesta.status_code == 400
    with usar_conjunto(mirador.id):
        assert not Area.objects.exists()


def test_crear_por_la_api_escribe_en_el_conjunto_activo(intruso, torres):
    respuesta = intruso.post(reverse("pruebas-areas"), {"nombre": "Salón comunal"}, format="json")

    assert respuesta.status_code == 201
    with usar_conjunto(torres.id):
        assert Area.objects.filter(nombre="Salón comunal").exists()


def test_sin_conjunto_activo_no_se_entra_a_datos_de_un_conjunto(torres, mirador):
    crear_usuario("laura@correo.com", (Rol.RESIDENTE, torres), (Rol.RESIDENTE, mirador))
    cliente = cliente_para("laura@correo.com")

    assert cliente.get(reverse("pruebas-areas")).status_code == 403


def test_al_retirar_el_rol_pierde_el_conjunto_activo_de_inmediato(intruso):
    Asignacion.objects.update(vigencia_hasta=timezone.localdate())

    assert intruso.get(reverse("pruebas-areas")).status_code == 403


def test_al_cambiar_de_conjunto_activo_solo_ve_los_datos_del_nuevo(torres, mirador):
    crear_usuario("laura@correo.com", (Rol.ADMINISTRACION, torres), (Rol.RESIDENTE, mirador))
    crear_area(torres, "Salón comunal")
    crear_area(mirador, "Piscina")
    cliente = cliente_para("laura@correo.com")

    cliente.post("/auth/conjunto-activo/", {"conjunto": str(torres.id)}, format="json")
    en_torres = [area["nombre"] for area in cliente.get(reverse("pruebas-areas")).json()]
    cliente.post("/auth/conjunto-activo/", {"conjunto": str(mirador.id)}, format="json")
    en_mirador = [area["nombre"] for area in cliente.get(reverse("pruebas-areas")).json()]

    assert en_torres == ["Salón comunal"]
    assert en_mirador == ["Piscina"]


# Prueba transversal de rutas


def rutas_de_la_api(patrones):
    for patron in patrones:
        if isinstance(patron, URLResolver):
            yield from rutas_de_la_api(patron.url_patterns)
        elif hasattr(patron.callback, "cls"):  # solo las vistas de DRF
            yield patron.name, patron.callback.cls


def rutas_sin_cubrir(rutas):
    con_prueba_del_intruso = set(DETALLES) | set(LISTADOS) | set(ACCIONES)
    faltantes = []
    for nombre, vista in rutas:
        if issubclass(vista, VistaDeConjunto):
            if nombre not in con_prueba_del_intruso:
                faltantes.append(nombre)
        elif nombre not in RUTAS_SIN_CONJUNTO:
            faltantes.append(nombre)
    return faltantes


def test_toda_ruta_de_la_api_esta_cubierta():
    assert rutas_sin_cubrir(rutas_de_la_api(get_resolver().url_patterns)) == []


def test_la_revision_detecta_una_ruta_nueva_sin_cubrir():
    class VistaNuevaDeConjunto(VistaDeConjunto):
        pass

    class VistaNuevaSinBase(APIView):
        pass

    rutas = [("ruta-nueva-de-conjunto", VistaNuevaDeConjunto), ("ruta-nueva-sin-base", VistaNuevaSinBase)]

    assert rutas_sin_cubrir(rutas) == ["ruta-nueva-de-conjunto", "ruta-nueva-sin-base"]
