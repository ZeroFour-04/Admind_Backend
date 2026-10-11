"""La validación compartida de un comprobante (HU-16). No toca la base: son funciones puras."""
import hashlib

import pytest

from apps.comun.archivos import comprobantes
from apps.comun.archivos.comprobantes import ArchivoInvalido, tipo_real, validar_comprobante

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 16


@pytest.mark.parametrize(
    "contenido, tipo",
    [(PDF, "application/pdf"), (PNG, "image/png"), (JPG, "image/jpeg")],
)
def test_un_pdf_un_png_y_un_jpg_pasan_con_su_tipo_real(contenido, tipo):
    datos = validar_comprobante(contenido)

    assert datos["tipo"] == tipo
    assert datos["peso"] == len(contenido)


def test_la_huella_es_la_sha256_del_contenido():
    assert validar_comprobante(PDF)["huella"] == hashlib.sha256(PDF).hexdigest()


def test_un_texto_llamado_pago_pdf_no_pasa():
    """El nombre no cuenta: solo la firma. Un texto con extensión `.pdf` sigue siendo un texto."""
    with pytest.raises(ArchivoInvalido) as error:
        validar_comprobante(b"esto no es un pdf, aunque se llame pago.pdf")

    assert error.value.mensaje == "El comprobante debe ser un PDF o una imagen JPG o PNG."


def test_una_imagen_que_se_hace_pasar_por_pdf_queda_con_su_tipo_real():
    assert tipo_real(PNG) == "image/png"


@pytest.mark.parametrize("contenido", [b"<svg xmlns='http://www.w3.org/2000/svg'/>", b"GIF89a....", b"RIFF....WEBP"])
def test_otros_formatos_no_sirven(contenido):
    assert tipo_real(contenido) is None
    with pytest.raises(ArchivoInvalido):
        validar_comprobante(contenido)


def test_el_limite_es_de_5_mb_y_un_byte_mas_no_pasa():
    limite = comprobantes.TAMANO_MAXIMO_DE_COMPROBANTE
    justo = PDF + b"0" * (limite - len(PDF))

    assert validar_comprobante(justo)["peso"] == limite
    with pytest.raises(ArchivoInvalido) as error:
        validar_comprobante(justo + b"0")
    assert error.value.mensaje == "El comprobante no puede pesar más de 5 MB."


def test_un_archivo_vacio_no_pasa():
    with pytest.raises(ArchivoInvalido) as error:
        validar_comprobante(b"")

    assert error.value.mensaje == "El archivo está vacío."


def test_acepta_el_contenido_que_devuelve_postgresql_como_memoryview():
    assert tipo_real(memoryview(PDF)) == "application/pdf"
