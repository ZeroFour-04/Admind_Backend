"""Pruebas del reglamento del conjunto (HU-33, lo mínimo que exige HU-03)."""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.auditoria.models import Registro
from apps.comun.aislamiento.contexto import usar_conjunto
from apps.conjuntos.models import Conjunto
from apps.cuentas.models import TokenDeSesion, Usuario
from apps.documentos.models import Reglamento
from apps.documentos.servicios import TAMANO_MAXIMO
from apps.permisos.catalogo import Rol
from apps.permisos.models import Asignacion
from apps.personas.models import Persona, TipoDocumento

pytestmark = pytest.mark.django_db

CONTRASENA = "una-clave-larga-2026"
PDF = b"%PDF-1.7 reglamento de prueba"


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


def reglamentos_de(conjunto):
    with usar_conjunto(conjunto.id):
        return list(Reglamento.objects.defer("contenido").order_by("subido_en"))


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


def subir(cliente, contenido=PDF, nombre="reglamento.pdf"):
    archivo = SimpleUploadedFile(nombre, contenido, content_type="application/pdf")
    return cliente.put("/documentos/reglamento/", {"archivo": archivo}, format="multipart")


def test_el_reglamento_se_sube_se_ve_y_se_descarga(admin, torres):
    assert admin.get("/documentos/reglamento/").json() == {"cargado": False}

    respuesta = subir(admin)

    assert respuesta.status_code == 200
    assert (respuesta.json()["cargado"], respuesta.json()["nombre"], respuesta.json()["peso"]) == (
        True, "reglamento.pdf", len(PDF)
    )
    assert admin.get("/documentos/reglamento/").json()["subido_por"] == "Laura Gómez"
    descarga = admin.get("/documentos/reglamento/archivo/")
    assert (descarga.status_code, descarga["Content-Type"], descarga.content) == (200, "application/pdf", PDF)
    with usar_conjunto(torres.id):
        assert [registro.accion for registro in Registro.objects.all()] == ["reglamento.subir"]


def test_un_texto_con_nombre_de_pdf_no_se_acepta(admin, torres):
    respuesta = subir(admin, b"Esto es un texto, no un PDF")

    assert respuesta.status_code == 400
    assert respuesta.json()["archivo"] == ["El archivo no es un PDF."]
    assert reglamentos_de(torres) == []
    assert admin.get("/documentos/reglamento/archivo/").status_code == 404


def test_un_reglamento_que_pasa_del_tope_no_se_acepta(admin, torres):
    respuesta = subir(admin, PDF + b" " * (TAMANO_MAXIMO - len(PDF) + 1))

    assert respuesta.status_code == 400
    assert respuesta.json()["archivo"] == ["El reglamento no puede pesar más de 10 MB."]
    assert reglamentos_de(torres) == []


def test_subir_otro_reglamento_conserva_el_anterior_y_el_vigente_es_el_nuevo(admin, torres):
    subir(admin)
    reformado = PDF + b", con la reforma de 2026"

    respuesta = subir(admin, reformado, "reglamento-2026.pdf")

    assert respuesta.json()["nombre"] == "reglamento-2026.pdf"
    assert [reglamento.nombre for reglamento in reglamentos_de(torres)] == ["reglamento.pdf", "reglamento-2026.pdf"]
    assert admin.get("/documentos/reglamento/archivo/").content == reformado


def test_el_residente_ve_los_datos_pero_no_sube_ni_descarga(admin, residente, torres):
    subir(admin)

    assert residente.get("/documentos/reglamento/").json()["nombre"] == "reglamento.pdf"
    assert subir(residente).status_code == 403
    assert residente.get("/documentos/reglamento/archivo/").status_code == 403
    assert len(reglamentos_de(torres)) == 1
