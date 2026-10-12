"""Creación y privacidad de casos y sus imágenes."""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.casos.models import Caso, FotoDeCaso
from apps.comun.aislamiento.contexto import usar_conjunto
from apps.conjuntos.models import Conjunto
from apps.cuentas.models import TokenDeSesion, Usuario
from apps.permisos.catalogo import Rol
from apps.permisos.models import Asignacion
from apps.personas.models import Persona, TipoDocumento
from apps.unidades.models import TipoVinculo, Unidad, VinculoUnidad

pytestmark = pytest.mark.django_db

CONTRASENA = "una-clave-larga-2026"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def crear_persona(conjunto, correo, nombres, rol=Rol.RESIDENTE):
    persona = Persona.objects.create(
        tipo_documento=TipoDocumento.CC,
        numero_documento=str(Persona.objects.count() + 1023456789),
        nombres=nombres,
        apellidos="Gómez",
    )
    with usar_conjunto(conjunto.id):
        Asignacion.objects.create(persona=persona, rol=rol, conjunto=conjunto)
    Usuario.objects.create_user(correo, CONTRASENA, persona)
    return persona


def cliente_para(correo):
    cliente = APIClient()
    respuesta = cliente.post("/auth/login/", {"correo": correo, "contrasena": CONTRASENA}, format="json")
    cliente.credentials(HTTP_AUTHORIZATION=f"Token {respuesta.json()['token']}")
    TokenDeSesion.objects.filter(usuario__correo=correo).update(dos_factores_verificado=True)
    return cliente


@pytest.fixture
def contexto():
    conjunto = Conjunto.objects.create(nombre="Torres del Río")
    residente = crear_persona(conjunto, "vecino@torres.com", "Pedro")
    return conjunto, residente, cliente_para("vecino@torres.com")


@pytest.fixture
def otro_residente(contexto):
    conjunto, _, _ = contexto
    crear_persona(conjunto, "otra@torres.com", "Lucía")
    return cliente_para("otra@torres.com")


def test_residente_crea_un_caso_con_foto_y_puede_consultarlo(contexto):
    conjunto, _, cliente = contexto
    imagen = SimpleUploadedFile("evidencia.png", PNG, content_type="image/png")

    respuesta = cliente.post(
        "/casos/",
        {"titulo": "Fuga de agua", "caso": "Hay una fuga en el pasillo.", "foto": imagen},
        format="multipart",
    )

    assert respuesta.status_code == 201
    datos = respuesta.json()
    assert (datos["titulo"], datos["cuerpo"], datos["estado"], datos["prioridad"]) == (
        "Fuga de agua", "Hay una fuga en el pasillo.", "ABIERTO", "NORMAL"
    )
    assert datos["autor"] == "Pedro Gómez" and datos["foto_id"]
    listado = cliente.get("/casos/")
    assert [caso["id"] for caso in listado.json()] == [datos["id"]]
    foto = cliente.get(f"/casos/{datos['id']}/fotos/{datos['foto_id']}/")
    assert foto.status_code == 200 and foto["Content-Type"] == "image/png" and foto.content == PNG
    with usar_conjunto(conjunto.id):
        assert Caso.objects.count() == 1 and FotoDeCaso.objects.count() == 1


def test_crear_caso_sin_imagen_es_valido(contexto):
    _, _, cliente = contexto

    respuesta = cliente.post(
        "/casos/",
        {"titulo": "Ruido", "caso": "Hay ruidos fuera de horario."},
        format="multipart",
    )

    assert respuesta.status_code == 201
    assert respuesta.json()["foto_id"] is None


def test_se_rechaza_archivo_que_no_es_imagen_sin_guardar_el_caso(contexto):
    conjunto, _, cliente = contexto
    archivo = SimpleUploadedFile("foto.png", b"esto no es una imagen", content_type="image/png")

    respuesta = cliente.post(
        "/casos/",
        {"titulo": "Daño", "caso": "Se dañó la puerta.", "foto": archivo},
        format="multipart",
    )

    assert respuesta.status_code == 400 and "foto" in respuesta.json()
    with usar_conjunto(conjunto.id):
        assert not Caso.objects.exists() and not FotoDeCaso.objects.exists()


def test_residente_no_puede_consultar_caso_ni_foto_de_otra_persona(contexto, otro_residente):
    _, _, cliente = contexto
    caso = cliente.post(
        "/casos/",
        {
            "titulo": "Daño",
            "caso": "Se dañó la puerta.",
            "foto": SimpleUploadedFile("foto.png", PNG, content_type="image/png"),
        },
        format="multipart",
    ).json()

    assert otro_residente.get("/casos/").json() == []
    assert otro_residente.get(
        f"/casos/{caso['id']}/fotos/{caso['foto_id']}/"
    ).status_code == 404


def test_secretaria_ve_todos_los_casos_con_residente_apartamento_y_fecha(contexto):
    conjunto, residente, cliente_residente = contexto
    caso = cliente_residente.post(
        "/casos/",
        {"titulo": "Fuga de agua", "caso": "Hay una fuga en el pasillo."},
        format="multipart",
    ).json()
    with usar_conjunto(conjunto.id):
        unidad = Unidad.objects.create(nombre="Torre 1 - Apto 402")
        VinculoUnidad.objects.create(
            persona=residente,
            unidad=unidad,
            tipo=TipoVinculo.ARRENDATARIO,
            reside=True,
        )
    crear_persona(conjunto, "secretaria@torres.com", "María", rol=Rol.SECRETARIA)
    cliente_secretaria = cliente_para("secretaria@torres.com")

    respuesta = cliente_secretaria.get("/casos/")

    assert respuesta.status_code == 200
    assert respuesta.json() == [{
        **caso,
        "apartamento": "Torre 1 - Apto 402",
    }]


def test_secretaria_rechaza_con_motivo_y_el_residente_puede_consultarlo(contexto):
    conjunto, _, cliente_residente = contexto
    caso = cliente_residente.post(
        "/casos/",
        {"titulo": "Fuga de agua", "caso": "Hay una fuga en el pasillo."},
        format="multipart",
    ).json()
    crear_persona(conjunto, "secretaria@torres.com", "María", rol=Rol.SECRETARIA)
    cliente_secretaria = cliente_para("secretaria@torres.com")

    rechazo = cliente_secretaria.post(
        f"/casos/{caso['id']}/rechazar/",
        {"motivo": "Este reporte debe registrarse con mantenimiento."},
        format="json",
    )

    assert rechazo.status_code == 200
    assert rechazo.json()["estado"] == "RECHAZADO"
    assert rechazo.json()["motivo_rechazo"] == "Este reporte debe registrarse con mantenimiento."
    caso_residente = cliente_residente.get("/casos/").json()[0]
    assert caso_residente["motivo_rechazo"] == "Este reporte debe registrarse con mantenimiento."


def test_se_rechaza_motivo_vacio_y_redirigir_lo_ve_solo_administracion(contexto):
    conjunto, _, cliente_residente = contexto
    abierto = cliente_residente.post(
        "/casos/",
        {"titulo": "Ruido", "caso": "Hay ruidos fuera de horario."},
        format="multipart",
    ).json()
    redirigido = cliente_residente.post(
        "/casos/",
        {"titulo": "Fuga", "caso": "Hay una fuga."},
        format="multipart",
    ).json()
    crear_persona(conjunto, "secretaria@torres.com", "María", rol=Rol.SECRETARIA)
    crear_persona(conjunto, "admin@torres.com", "Ana", rol=Rol.ADMINISTRACION)
    cliente_secretaria = cliente_para("secretaria@torres.com")
    cliente_admin = cliente_para("admin@torres.com")

    rechazo = cliente_secretaria.post(
        f"/casos/{abierto['id']}/rechazar/",
        {"motivo": "   "},
        format="json",
    )
    redireccion = cliente_secretaria.post(f"/casos/{redirigido['id']}/redirigir/")

    assert rechazo.status_code == 400
    assert redireccion.status_code == 200
    assert redireccion.json()["estado"] == "REDIRIGIDO"
    casos_admin = cliente_admin.get("/casos/")
    assert casos_admin.status_code == 200
    assert [caso["id"] for caso in casos_admin.json()] == [redirigido["id"]]


def test_superusuario_ve_casos_abiertos_rechazados_y_redirigidos(contexto):
    conjunto, residente, cliente_residente = contexto
    abierto = cliente_residente.post(
        "/casos/",
        {"titulo": "Abierto", "caso": "Pendiente"},
        format="multipart",
    ).json()
    rechazado = cliente_residente.post(
        "/casos/",
        {"titulo": "Rechazado", "caso": "Con motivo"},
        format="multipart",
    ).json()
    redirigido = cliente_residente.post(
        "/casos/",
        {"titulo": "Redirigido", "caso": "Enviado a administración"},
        format="multipart",
    ).json()
    crear_persona(conjunto, "secretaria@torres.com", "María", rol=Rol.SECRETARIA)
    secretaria = cliente_para("secretaria@torres.com")
    secretaria.post(
        f"/casos/{rechazado['id']}/rechazar/",
        {"motivo": "No contiene información suficiente."},
        format="json",
    )
    secretaria.post(f"/casos/{redirigido['id']}/redirigir/")

    superusuario = Persona.objects.create(
        tipo_documento=TipoDocumento.CC,
        numero_documento=str(Persona.objects.count() + 1023456789),
        nombres="Sofía",
        apellidos="Global",
    )
    Asignacion.objects.create(persona=superusuario, rol=Rol.SUPERUSUARIO)
    Usuario.objects.create_user("super@torres.com", CONTRASENA, superusuario)
    cliente_superusuario = cliente_para("super@torres.com")
    TokenDeSesion.objects.filter(usuario__correo="super@torres.com").update(conjunto_activo=conjunto)

    respuesta = cliente_superusuario.get("/casos/")

    assert respuesta.status_code == 200
    casos = {caso["id"]: caso for caso in respuesta.json()}
    assert set(casos) == {abierto["id"], rechazado["id"], redirigido["id"]}
    assert casos[abierto["id"]]["estado"] == "ABIERTO"
    assert casos[rechazado["id"]]["estado"] == "RECHAZADO"
    assert casos[redirigido["id"]]["estado"] == "REDIRIGIDO"

