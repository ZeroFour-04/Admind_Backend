"""Pruebas de HU-21: identidad visual del conjunto, con su color (del catálogo o propio) y su foto 1:1.

El contraste del texto sobre cada uno de los ocho acentos se prueba en el frontend, que es
donde vive la paleta.
"""
import hashlib
import struct

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.comun.aislamiento.contexto import usar_conjunto
from apps.conjuntos import servicios
from apps.conjuntos.models import Conjunto, LogoDeConjunto
from apps.cuentas.models import TokenDeSesion, Usuario
from apps.permisos.catalogo import Rol
from apps.permisos.models import Asignacion
from apps.personas.models import Persona, TipoDocumento

pytestmark = pytest.mark.django_db

CONTRASENA = "una-clave-larga-2026"
IDENTIDAD = "/conjuntos/actual/identidad/"
LOGO = "/conjuntos/actual/identidad/logo/"

# Basta con la firma y la cabecera con el tamaño: el servicio lee esos bytes, no dibuja la imagen.


def png(ancho, alto):
    ihdr = struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", ancho, alto) + b"\x08\x06\x00\x00\x00"
    return b"\x89PNG\r\n\x1a\n" + ihdr + b"\x00" * 32


def jpg(ancho, alto):
    # Inicio, un segmento APP0 que hay que saltar y el inicio de cuadro con alto y ancho.
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9
    sof = b"\xff\xc0" + struct.pack(">HBHH", 17, 8, alto, ancho) + b"\x00" * 10
    return b"\xff\xd8" + app0 + sof + b"\x00" * 16


def webp(ancho, alto, variante="VP8 "):
    if variante == "VP8 ":
        cuerpo = b"\x00\x00\x00\x9d\x01\x2a" + struct.pack("<HH", ancho, alto)
    elif variante == "VP8L":
        cuerpo = b"\x2f" + ((ancho - 1) | (alto - 1) << 14).to_bytes(4, "little")
    else:
        cuerpo = b"\x00" * 4 + (ancho - 1).to_bytes(3, "little") + (alto - 1).to_bytes(3, "little")
    return b"RIFF\x40\x00\x00\x00WEBP" + variante.encode() + b"\x00" * 4 + cuerpo + b"\x00" * 32


PNG = png(64, 64)
JPG = jpg(64, 64)
WEBP = webp(64, 64)


def huella(contenido):
    return hashlib.sha256(contenido).hexdigest()


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


def subir(cliente, contenido, nombre="logo.png", tipo="image/png"):
    archivo = SimpleUploadedFile(nombre, contenido, content_type=tipo)
    return cliente.put(LOGO, {"archivo": archivo}, format="multipart")


def con_logo(conjunto, contenido):
    with usar_conjunto(conjunto.id):
        return servicios.guardar_logo(conjunto, contenido)


@pytest.fixture
def torres():
    return Conjunto.objects.create(nombre="Torres del Río", direccion="Calle 1")


@pytest.fixture
def admin(torres):
    crear_persona("admin@torres.com", (Rol.ADMINISTRACION, torres))
    return cliente_para("admin@torres.com")


# Logo


def test_administracion_sube_el_logo_y_se_sirve_por_su_huella(admin, torres):
    respuesta = subir(admin, PNG)

    assert respuesta.status_code == 200
    assert respuesta.json()["logo"] == huella(PNG)
    torres.refresh_from_db()
    assert torres.logo_huella == huella(PNG)
    imagen = admin.get(f"/conjuntos/logos/{huella(PNG)}/")
    assert imagen.status_code == 200
    assert imagen["Content-Type"] == "image/png"
    assert imagen.content == PNG


@pytest.mark.parametrize(
    ("contenido", "tipo"), [(PNG, "image/png"), (JPG, "image/jpeg"), (WEBP, "image/webp")]
)
def test_el_tipo_se_toma_de_la_firma_y_no_de_lo_que_dice_el_navegador(admin, torres, contenido, tipo):
    respuesta = subir(admin, contenido, nombre="logo.bin", tipo="application/octet-stream")

    assert respuesta.status_code == 200
    with usar_conjunto(torres.id):
        assert LogoDeConjunto.objects.get().tipo == tipo


@pytest.mark.parametrize(
    "contenido",
    [
        b"hola, no soy una imagen",
        b"%PDF-1.7 documento renombrado",
        b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
    ],
)
def test_un_archivo_que_no_es_imagen_se_rechaza_por_su_tipo_real(admin, torres, contenido):
    respuesta = subir(admin, contenido, nombre="logo.png", tipo="image/png")

    assert respuesta.status_code == 400
    assert respuesta.json()["archivo"] == ["El archivo no es una imagen PNG, JPG o WebP."]
    torres.refresh_from_db()
    assert torres.logo_huella == ""


@pytest.mark.parametrize(
    "contenido",
    [png(64, 64), jpg(300, 300), webp(128, 128), webp(128, 128, "VP8L"), webp(512, 512, "VP8X")],
)
def test_una_foto_cuadrada_se_acepta_en_cualquiera_de_los_tres_formatos(admin, torres, contenido):
    assert subir(admin, contenido).status_code == 200


@pytest.mark.parametrize(
    "contenido",
    [png(640, 480), jpg(300, 301), webp(128, 64), webp(64, 128, "VP8L"), webp(1024, 512, "VP8X")],
)
def test_una_foto_que_no_es_cuadrada_se_rechaza_con_su_tamano(admin, torres, contenido):
    respuesta = subir(admin, contenido)

    assert respuesta.status_code == 400
    assert respuesta.json()["archivo"][0].startswith("La foto debe ser cuadrada (1:1). Esta mide ")
    torres.refresh_from_db()
    assert torres.logo_huella == ""


def test_una_imagen_con_la_firma_pero_sin_cabecera_legible_se_rechaza(admin, torres):
    respuesta = subir(admin, b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)

    assert respuesta.status_code == 400
    assert respuesta.json()["archivo"] == ["No se pudo leer el tamaño de la imagen."]


def test_un_logo_mas_pesado_que_el_limite_se_rechaza(admin, torres):
    pesado = PNG + b"\x00" * servicios.TAMANO_MAXIMO_LOGO

    respuesta = subir(admin, pesado)

    assert respuesta.status_code == 400
    assert "512 KB" in respuesta.json()["archivo"][0]
    torres.refresh_from_db()
    assert torres.logo_huella == ""


def test_conjunto_sin_logo_responde_logo_nulo_y_no_una_ruta_rota(admin):
    assert admin.get(IDENTIDAD).json()["logo"] is None
    assert admin.get("/auth/conjuntos/").json()[0]["logo"] is None


def test_reemplazar_el_logo_cambia_la_huella_y_la_anterior_deja_de_servirse(admin, torres):
    subir(admin, PNG)

    respuesta = subir(admin, JPG, nombre="logo.jpg", tipo="image/jpeg")

    assert respuesta.json()["logo"] == huella(JPG)
    assert admin.get(f"/conjuntos/logos/{huella(PNG)}/").status_code == 404
    assert admin.get(f"/conjuntos/logos/{huella(JPG)}/").content == JPG
    with usar_conjunto(torres.id):
        assert LogoDeConjunto.objects.count() == 1


def test_quitar_el_logo_vuelve_al_nombre(admin, torres):
    subir(admin, PNG)

    respuesta = admin.delete(LOGO)

    assert respuesta.status_code == 200
    assert respuesta.json()["logo"] is None
    assert admin.get(f"/conjuntos/logos/{huella(PNG)}/").status_code == 404
    with usar_conjunto(torres.id):
        assert not LogoDeConjunto.objects.exists()


def test_el_logo_de_un_conjunto_ajeno_no_se_entrega_aunque_se_conozca_la_huella(admin):
    mirador = Conjunto.objects.create(nombre="Mirador")
    con_logo(mirador, PNG)

    assert admin.get(f"/conjuntos/logos/{huella(PNG)}/").status_code == 404


def test_el_selector_trae_el_logo_de_cada_conjunto_aunque_no_sea_el_activo(torres):
    mirador = Conjunto.objects.create(nombre="Mirador")
    con_logo(torres, PNG)
    con_logo(mirador, JPG)
    crear_persona("laura@correo.com", (Rol.RESIDENTE, torres), (Rol.RESIDENTE, mirador))
    # Con dos conjuntos entra sin conjunto activo, que es cuando ve el selector.
    cliente = cliente_para("laura@correo.com")

    logos = {c["nombre"]: c["logo"] for c in cliente.get("/auth/conjuntos/").json()}

    assert logos == {"Mirador": huella(JPG), "Torres del Río": huella(PNG)}
    assert cliente.get(f"/conjuntos/logos/{huella(JPG)}/").content == JPG


# Color


def test_el_color_se_elige_solo_del_catalogo(admin, torres):
    assert admin.patch(IDENTIDAD, {"acento": "fucsia"}, format="json").status_code == 400

    respuesta = admin.patch(IDENTIDAD, {"acento": "vino"}, format="json")

    assert respuesta.status_code == 200
    assert respuesta.json()["acento"] == "vino"
    torres.refresh_from_db()
    assert torres.acento == "vino"


def test_un_color_propio_se_guarda_con_el_acento_personalizado(admin, torres):
    respuesta = admin.patch(IDENTIDAD, {"acento": "personalizado", "color": "#1A8FE3"}, format="json")

    assert respuesta.status_code == 200
    assert (respuesta.json()["acento"], respuesta.json()["color"]) == ("personalizado", "#1a8fe3")
    torres.refresh_from_db()
    assert (torres.acento, torres.color_personalizado) == ("personalizado", "#1a8fe3")
    # El color viaja también en el listado del selector, que pinta cada tarjeta.
    assert admin.get("/auth/conjuntos/").json()[0]["color"] == "#1a8fe3"


def test_un_color_muy_claro_tambien_se_guarda(admin):
    # Se pierde contraste con el texto blanco, pero la API no lo prohíbe: la pantalla solo lo advierte.
    assert admin.patch(IDENTIDAD, {"acento": "personalizado", "color": "#fff8c4"}, format="json").status_code == 200


@pytest.mark.parametrize(
    "datos",
    [
        {"acento": "personalizado"},
        {"acento": "personalizado", "color": "azul"},
        {"acento": "personalizado", "color": "#12345"},
        {"acento": "vino", "color": "#1a8fe3"},
    ],
)
def test_el_personalizado_va_con_un_hex_y_los_del_catalogo_sin_color(admin, torres, datos):
    respuesta = admin.patch(IDENTIDAD, datos, format="json")

    assert respuesta.status_code == 400
    assert "color" in respuesta.json()
    torres.refresh_from_db()
    assert (torres.acento, torres.color_personalizado) == ("verde", "")


def test_volver_a_un_acento_del_catalogo_borra_el_color_propio(admin, torres):
    admin.patch(IDENTIDAD, {"acento": "personalizado", "color": "#1a8fe3"}, format="json")

    respuesta = admin.patch(IDENTIDAD, {"acento": "ocre"}, format="json")

    assert respuesta.json()["color"] is None
    torres.refresh_from_db()
    assert (torres.acento, torres.color_personalizado) == ("ocre", "")


# Permisos


@pytest.mark.parametrize("rol", [Rol.RESIDENTE, Rol.SECRETARIA, Rol.VIGILANCIA])
def test_sin_conjunto_branding_no_cambia_el_color_ni_el_logo(torres, rol):
    crear_persona("vecino@torres.com", (rol, torres))
    cliente = cliente_para("vecino@torres.com")

    assert cliente.patch(IDENTIDAD, {"acento": "vino"}, format="json").status_code == 403
    assert subir(cliente, PNG).status_code == 403
    assert cliente.delete(LOGO).status_code == 403
    torres.refresh_from_db()
    assert (torres.acento, torres.logo_huella) == ("verde", "")


def test_sin_conjunto_branding_tampoco_cambia_el_color_por_el_asistente(torres):
    crear_persona("vecino@torres.com", (Rol.RESIDENTE, torres))
    cliente = cliente_para("vecino@torres.com")

    assert cliente.patch("/conjuntos/actual/", {"acento": "vino"}, format="json").status_code == 403
    assert cliente.patch("/conjuntos/actual/", {"color": "#1a8fe3"}, format="json").status_code == 403
