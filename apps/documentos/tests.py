"""Pruebas de los documentos del conjunto: reglamento y manual de convivencia (HU-33, sin actas)."""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.urls import URLResolver, get_resolver
from rest_framework.test import APIClient

from apps.auditoria.models import Registro
from apps.comun.aislamiento.contexto import usar_conjunto
from apps.conjuntos.models import Conjunto
from apps.cuentas.models import TokenDeSesion, Usuario
from apps.documentos.models import Documento, TipoDeDocumento
from apps.documentos.servicios import TAMANO_MAXIMO
from apps.permisos.catalogo import Rol
from apps.permisos.models import Asignacion
from apps.personas.models import Persona, TipoDocumento

pytestmark = pytest.mark.django_db

CONTRASENA = "una-clave-larga-2026"
PDF = b"%PDF-1.7 reglamento de prueba"
MANUAL = b"%PDF-1.7 manual de convivencia"


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


def documentos_de(conjunto, tipo=None):
    with usar_conjunto(conjunto.id):
        consulta = Documento.objects.defer("contenido").order_by("subido_en")
        return list(consulta.filter(tipo=tipo) if tipo else consulta)


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


def subir(cliente, contenido=PDF, nombre="reglamento.pdf", tipo="reglamento"):
    archivo = SimpleUploadedFile(nombre, contenido, content_type="application/pdf")
    return cliente.put(f"/documentos/{tipo}/", {"archivo": archivo}, format="multipart")


def acciones(conjunto):
    with usar_conjunto(conjunto.id):
        return list(Registro.objects.order_by("creado_en").values_list("accion", flat=True))


# El reglamento: lo que ya había, sobre la ruta por tipo


def test_el_reglamento_se_sube_se_ve_y_se_descarga(admin, torres):
    assert admin.get("/documentos/reglamento/").json()["cargado"] is False

    respuesta = subir(admin)

    assert respuesta.status_code == 200
    assert (respuesta.json()["cargado"], respuesta.json()["nombre"], respuesta.json()["peso"]) == (
        True, "reglamento.pdf", len(PDF)
    )
    assert respuesta.json()["tipo"] == "reglamento" and respuesta.json()["tipo_nombre"] == "Reglamento de propiedad horizontal"
    assert admin.get("/documentos/reglamento/").json()["subido_por"] == "Laura Gómez"
    descarga = admin.get("/documentos/reglamento/archivo/")
    assert (descarga.status_code, descarga["Content-Type"], descarga.content) == (200, "application/pdf", PDF)
    assert acciones(torres) == ["documento.subir", "documento.descargar"]


def test_hu33_un_archivo_que_no_es_pdf_se_rechaza_por_su_tipo_real(admin, torres):
    # Con nombre y tipo de PDF: lo que decide es la firma del contenido, no la extensión ni lo que dice el navegador.
    respuesta = subir(admin, b"Esto es un texto, no un PDF", nombre="reglamento.pdf")

    assert respuesta.status_code == 400
    assert respuesta.json()["archivo"] == ["El archivo no es un PDF."]
    assert documentos_de(torres) == []
    assert admin.get("/documentos/reglamento/archivo/").status_code == 404
    assert subir(admin, b"texto", nombre="manual.pdf", tipo="manual").status_code == 400


def test_un_documento_que_pasa_del_tope_no_se_acepta(admin, torres):
    respuesta = subir(admin, PDF + b" " * (TAMANO_MAXIMO - len(PDF) + 1))

    assert respuesta.status_code == 400
    assert respuesta.json()["archivo"] == ["El reglamento de propiedad horizontal no puede pesar más de 10 MB."]
    assert documentos_de(torres) == []


def test_un_archivo_vacio_no_se_acepta(admin, torres):
    assert subir(admin, b"").status_code == 400
    assert documentos_de(torres) == []


# El manual de convivencia y la lista por tipo


def test_hu33_el_residente_ve_el_reglamento_y_el_manual_vigentes(admin, residente):
    subir(admin)
    subir(admin, MANUAL, "manual.pdf", "manual")

    lista = residente.get("/documentos/")

    assert lista.status_code == 200
    assert [(d["tipo"], d["cargado"], d.get("nombre")) for d in lista.json()] == [
        ("reglamento", True, "reglamento.pdf"),
        ("manual", True, "manual.pdf"),
    ]
    assert residente.get("/documentos/manual/").json()["tipo_nombre"] == "Manual de convivencia"


def test_la_lista_dice_cual_tipo_no_se_ha_cargado(admin, residente):
    subir(admin)

    lista = residente.get("/documentos/").json()

    assert [(d["tipo"], d["cargado"]) for d in lista] == [("reglamento", True), ("manual", False)]
    assert residente.get("/documentos/manual/archivo/").status_code == 404


def test_cada_tipo_tiene_su_propio_vigente(admin, torres):
    subir(admin)
    subir(admin, MANUAL, "manual.pdf", "manual")

    assert admin.get("/documentos/reglamento/archivo/").content == PDF
    assert admin.get("/documentos/manual/archivo/").content == MANUAL
    assert [d.tipo for d in documentos_de(torres)] == ["reglamento", "manual"]


def test_un_tipo_que_no_existe_ni_llega_a_la_vista(admin, residente):
    for ruta in ("actas", "contrato", "reglamentos"):
        assert admin.get(f"/documentos/{ruta}/").status_code == 404
        assert admin.get(f"/documentos/{ruta}/archivo/").status_code == 404
        assert admin.get(f"/documentos/{ruta}/versiones/").status_code == 404
        assert subir(admin, tipo=ruta).status_code == 404


def test_hu33_el_catalogo_de_tipos_no_trae_actas():
    assert TipoDeDocumento.values == ["reglamento", "manual"]


# Versiones


def test_hu33_una_version_nueva_archiva_la_anterior_sin_borrarla(admin, torres):
    subir(admin)
    reformado = PDF + b", con la reforma de 2026"

    respuesta = subir(admin, reformado, "reglamento-2026.pdf")

    assert respuesta.json()["nombre"] == "reglamento-2026.pdf"
    assert [d.nombre for d in documentos_de(torres, "reglamento")] == ["reglamento.pdf", "reglamento-2026.pdf"]
    assert admin.get("/documentos/reglamento/archivo/").content == reformado
    versiones = admin.get("/documentos/reglamento/versiones/").json()
    assert [(v["nombre"], v["vigente"]) for v in versiones] == [("reglamento-2026.pdf", True), ("reglamento.pdf", False)]


def test_las_versiones_de_un_tipo_no_mezclan_las_del_otro(admin):
    subir(admin)
    subir(admin, MANUAL, "manual.pdf", "manual")

    assert [v["nombre"] for v in admin.get("/documentos/manual/versiones/").json()] == ["manual.pdf"]


def test_administracion_descarga_una_version_archivada_y_queda_registrado(admin, torres):
    subir(admin)
    subir(admin, PDF + b" v2", "v2.pdf")
    primera = admin.get("/documentos/reglamento/versiones/").json()[1]

    respuesta = admin.get(f"/documentos/reglamento/versiones/{primera['id']}/archivo/")

    assert (respuesta.status_code, respuesta.content) == (200, PDF)
    with usar_conjunto(torres.id):
        registro = Registro.objects.get(accion="documento.descargar")
    assert str(registro.entidad_id) == primera["id"] and registro.detalle == {"tipo": "reglamento", "version": "archivada"}


def test_una_version_de_otro_tipo_no_se_encuentra_por_la_ruta_equivocada(admin):
    subir(admin)
    subir(admin, MANUAL, "manual.pdf", "manual")
    del_manual = admin.get("/documentos/manual/versiones/").json()[0]

    assert admin.get(f"/documentos/reglamento/versiones/{del_manual['id']}/archivo/").status_code == 404


# Permisos (D1 a)


def test_hu33_el_residente_descarga_el_vigente_y_no_las_versiones(admin, residente, torres):
    subir(admin)
    subir(admin, PDF + b" v2", "v2.pdf")
    primera = admin.get("/documentos/reglamento/versiones/").json()[1]

    assert residente.get("/documentos/reglamento/").json()["nombre"] == "v2.pdf"
    assert residente.get("/documentos/reglamento/archivo/").status_code == 200
    assert subir(residente).status_code == 403
    assert subir(residente, MANUAL, "manual.pdf", "manual").status_code == 403
    assert residente.get("/documentos/reglamento/versiones/").status_code == 403
    assert residente.get(f"/documentos/reglamento/versiones/{primera['id']}/archivo/").status_code == 403
    assert len(documentos_de(torres)) == 2


def test_hu33_cada_descarga_queda_en_la_auditoria(admin, residente, torres):
    subir(admin, MANUAL, "manual.pdf", "manual")
    with usar_conjunto(torres.id):
        persona = Persona.objects.get(asignaciones__rol=Rol.RESIDENTE)
        manual = Documento.objects.get(tipo="manual")

    residente.get("/documentos/manual/archivo/")

    with usar_conjunto(torres.id):
        descarga = Registro.objects.get(accion="documento.descargar")
    assert descarga.actor_id == persona.id and descarga.entidad_id == manual.id
    assert descarga.detalle == {"tipo": "manual", "version": "vigente"}
    # La fecha la pone el registro: quién, qué y cuándo.
    assert descarga.creado_en is not None


def test_subir_deja_el_registro_con_el_tipo(admin, torres):
    subir(admin, MANUAL, "manual.pdf", "manual")

    with usar_conjunto(torres.id):
        registro = Registro.objects.get(accion="documento.subir")
    assert registro.despues["tipo"] == "manual" and registro.despues["nombre"] == "manual.pdf"


def test_vigilancia_no_ve_los_documentos(torres):
    crear_usuario("vigilante@torres.com", Rol.VIGILANCIA, torres)
    vigilancia = cliente_para("vigilante@torres.com")

    assert vigilancia.get("/documentos/").status_code == 403
    assert vigilancia.get("/documentos/reglamento/archivo/").status_code == 403


# Lo que hace cumplir la base


def test_la_base_no_acepta_un_tipo_que_no_es_del_catalogo(torres):
    persona = crear_usuario("admin@torres.com", Rol.ADMINISTRACION, torres)
    with usar_conjunto(torres.id):
        with pytest.raises(IntegrityError), transaction.atomic():
            Documento.objects.create(
                tipo="acta", contenido=PDF, nombre="acta.pdf", peso=len(PDF), huella="a" * 64, subido_por=persona
            )


def test_hu33_la_migracion_renombra_la_tabla_y_conserva_los_reglamentos():
    from django.db import connection

    migracion = __import__(
        "apps.documentos.migrations.0002_documento_con_tipo", fromlist=["Migration"]
    ).Migration
    operaciones = [type(operacion).__name__ for operacion in migracion.operations]

    # Un RenameModel conserva las filas; un DeleteModel + CreateModel las perdería.
    assert operaciones[0] == "RenameModel" and "DeleteModel" not in operaciones and "CreateModel" not in operaciones
    with connection.cursor() as cursor:
        tablas = connection.introspection.table_names(cursor)
    assert "documentos_documento" in tablas and "documentos_reglamento" not in tablas


# Las rutas


def test_las_rutas_de_documentos_no_ofrecen_borrar():
    rutas = []

    def recorrer(patrones):
        for patron in patrones:
            if isinstance(patron, URLResolver):
                recorrer(patron.url_patterns)
            elif str(patron.callback.__module__).startswith("apps.documentos"):
                rutas.append((patron.name, {m.upper() for m in patron.callback.cls().allowed_methods}))

    recorrer(get_resolver().url_patterns)

    assert sorted(nombre for nombre, _ in rutas) == [
        "documento", "documento-archivo", "documento-version-archivo", "documento-versiones", "documentos",
    ]
    assert not [nombre for nombre, metodos in rutas if "DELETE" in metodos or "PATCH" in metodos]
