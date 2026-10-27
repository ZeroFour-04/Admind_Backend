"""Creación y privacidad de casos y sus imágenes, y el ciclo del caso (HU-29)."""
import uuid

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connection, transaction
from django.utils import timezone
from rest_framework.test import APIClient

from apps.auditoria.models import Registro
from apps.casos.models import Caso, FotoDeCaso
from apps.notificaciones.models import Notificacion
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


def abrir(cliente, titulo="Fuga de agua", texto="Hay una fuga en el pasillo."):
    return cliente.post("/casos/", {"titulo": titulo, "caso": texto}, format="multipart").json()


def accion(cliente, caso, nombre, **datos):
    return cliente.post(f"/casos/{caso['id']}/{nombre}/", datos, format="json")


def avisos_de(conjunto, caso):
    with usar_conjunto(conjunto.id):
        return [
            (aviso.persona.nombres, aviso.origen, aviso.titulo, aviso.cuerpo)
            for aviso in Notificacion.objects.filter(referencia=caso["id"]).order_by("creada_en")
        ]


@pytest.fixture
def gestion(contexto):
    """María es Secretaría y Ana es Administración en el conjunto del residente."""
    conjunto, _, _ = contexto
    crear_persona(conjunto, "secretaria@torres.com", "María", rol=Rol.SECRETARIA)
    crear_persona(conjunto, "admin@torres.com", "Ana", rol=Rol.ADMINISTRACION)
    return cliente_para("secretaria@torres.com"), cliente_para("admin@torres.com")


def test_gestion_ve_todos_los_casos_con_residente_apartamento_y_fecha(contexto, gestion):
    conjunto, residente, cliente_residente = contexto
    secretaria, administracion = gestion
    caso = abrir(cliente_residente)
    with usar_conjunto(conjunto.id):
        unidad = Unidad.objects.create(nombre="Torre 1 - Apto 402")
        VinculoUnidad.objects.create(
            persona=residente,
            unidad=unidad,
            tipo=TipoVinculo.ARRENDATARIO,
            reside=True,
        )

    de_secretaria = secretaria.get("/casos/")
    assert de_secretaria.status_code == 200
    (listado,) = de_secretaria.json()
    assert {campo: listado[campo] for campo in caso} == {**caso, "apartamento": "Torre 1 - Apto 402"}
    assert (listado["autor"], listado["estado_nombre"], listado["prioridad_nombre"]) == (
        "Pedro Gómez", "Por revisar", "Normal"
    )
    assert administracion.get("/casos/").json() == []

    accion(secretaria, caso, "redirigir")
    de_administracion = administracion.get("/casos/")
    assert [item["id"] for item in de_administracion.json()] == [caso["id"]]


def test_el_residente_no_ve_la_nota_interna_ni_quien_actuo(contexto, gestion):
    _, _, cliente_residente = contexto
    secretaria, administracion = gestion
    caso = abrir(cliente_residente)
    accion(secretaria, caso, "redirigir", nota="Parece urgente, ya van tres reportes.")
    accion(administracion, caso, "responder", respuesta="El plomero va mañana a las 8.")

    propio = cliente_residente.get(f"/casos/{caso['id']}/")
    de_gestion = secretaria.get(f"/casos/{caso['id']}/").json()

    assert propio.status_code == 200
    assert not {"nota_redireccion", "cerrado_por", "justificacion_prioridad"} & set(propio.json())
    assert (propio.json()["estado"], propio.json()["respuesta"]) == ("RESUELTO", "El plomero va mañana a las 8.")
    assert de_gestion["nota_redireccion"] == "Parece urgente, ya van tres reportes."
    assert de_gestion["cerrado_por"] == "Ana Gómez"


def test_un_residente_no_ve_el_detalle_del_caso_de_otro(contexto, otro_residente):
    _, _, cliente_residente = contexto
    caso = abrir(cliente_residente)

    assert otro_residente.get(f"/casos/{caso['id']}/").status_code == 404
    assert cliente_residente.get(f"/casos/{uuid.uuid4()}/").status_code == 404


def test_un_caso_creado_sin_prioridad_queda_en_normal_tambien_en_la_base(contexto):
    conjunto, residente, cliente_residente = contexto

    por_la_api = abrir(cliente_residente)
    sin_prioridad = uuid.uuid4()
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO casos_caso (id, conjunto_id, autor_id, titulo, cuerpo, estado, justificacion_prioridad, "
            "nota_redireccion, respuesta, motivo_rechazo, causal_rechazo, creado_en) "
            "VALUES (%s, %s, %s, 'Sin prioridad', 'Directo a la base', 'ABIERTO', '', '', '', '', '', %s)",
            [sin_prioridad, conjunto.id, residente.id, timezone.now()],
        )

    assert por_la_api["prioridad"] == "NORMAL"
    with usar_conjunto(conjunto.id):
        assert Caso.objects.get(pk=sin_prioridad).prioridad == "NORMAL"


def test_tomar_un_caso_lo_deja_en_revision_y_avisa_al_residente(contexto, gestion):
    conjunto, _, cliente_residente = contexto
    secretaria, administracion = gestion
    caso = abrir(cliente_residente)

    tomado = accion(secretaria, caso, "tomar")
    repetido = accion(administracion, caso, "tomar")

    assert (tomado.status_code, tomado.json()["estado"]) == (200, "EN_REVISION")
    assert repetido.status_code == 409
    assert accion(cliente_residente, caso, "tomar").status_code == 403
    assert avisos_de(conjunto, caso) == [
        ("Pedro", "caso.en_revision", "Tu caso está en revisión", "«Fuga de agua»."),
    ]


def test_secretaria_descarta_con_causal_y_motivo_y_el_residente_lo_consulta(contexto, gestion):
    conjunto, _, cliente_residente = contexto
    secretaria, _ = gestion
    caso = abrir(cliente_residente)

    descarte = accion(
        secretaria, caso, "descartar",
        causal="NO_ES_COMPETENCIA", motivo="Este reporte debe registrarse con mantenimiento.",
    )

    assert descarte.status_code == 200
    assert (descarte.json()["estado"], descarte.json()["causal_rechazo"]) == ("RECHAZADO", "NO_ES_COMPETENCIA")
    assert descarte.json()["cerrado_por"] == "María Gómez"
    caso_residente = cliente_residente.get("/casos/").json()[0]
    assert caso_residente["motivo_rechazo"] == "Este reporte debe registrarse con mantenimiento."
    assert caso_residente["causal_rechazo_nombre"] == "No es competencia de la administración"
    assert avisos_de(conjunto, caso) == [(
        "Pedro",
        "caso.rechazado",
        "Tu caso fue rechazado",
        "«Fuga de agua». Motivo: No es competencia de la administración. "
        "Este reporte debe registrarse con mantenimiento.",
    )]
    with usar_conjunto(conjunto.id):
        registro = Registro.objects.get(accion="caso.descartar", entidad_id=caso["id"])
    assert (registro.actor.nombres, registro.antes, registro.despues["estado"]) == (
        "María", {"estado": "ABIERTO"}, "RECHAZADO"
    )


def test_el_descarte_exige_causal_y_motivo_y_no_es_de_administracion(contexto, gestion):
    conjunto, _, cliente_residente = contexto
    secretaria, administracion = gestion
    caso = abrir(cliente_residente)

    sin_motivo = accion(secretaria, caso, "descartar", causal="DUPLICADO", motivo="   ")
    sin_causal = accion(secretaria, caso, "descartar", motivo="Ya está reportado.")
    con_otra = accion(secretaria, caso, "descartar", causal="OTRO", motivo="No me parece.")
    de_administracion = accion(administracion, caso, "descartar", causal="DUPLICADO", motivo="Ya está reportado.")

    assert sin_motivo.status_code == 400 and "motivo" in sin_motivo.json()
    assert sin_causal.status_code == 400 and "causal" in sin_causal.json()
    assert con_otra.status_code == 400 and "causal" in con_otra.json()
    assert de_administracion.status_code == 403
    with usar_conjunto(conjunto.id):
        assert Caso.objects.get(pk=caso["id"]).estado == "ABIERTO"


def test_secretaria_redirige_y_no_puede_responder_ni_tocar_lo_ya_redirigido(contexto, gestion):
    conjunto, _, cliente_residente = contexto
    secretaria, _ = gestion
    caso = abrir(cliente_residente)

    redireccion = accion(secretaria, caso, "redirigir", nota="Revisar con el contratista.")
    responder = accion(secretaria, caso, "responder", respuesta="Ya quedó.")
    rechazar = accion(secretaria, caso, "rechazar", motivo="No aplica.")
    descartar = accion(secretaria, caso, "descartar", causal="DUPLICADO", motivo="Ya está reportado.")
    otra_vez = accion(secretaria, caso, "redirigir")

    assert (redireccion.status_code, redireccion.json()["estado"]) == (200, "REDIRIGIDO")
    assert redireccion.json()["nota_redireccion"] == "Revisar con el contratista."
    assert (responder.status_code, rechazar.status_code) == (403, 403)
    assert (descartar.status_code, otra_vez.status_code) == (409, 409)
    assert avisos_de(conjunto, caso) == [
        ("Pedro", "caso.redirigido", "Tu caso pasó a la administración", "«Fuga de agua»."),
    ]


def test_un_caso_no_se_resuelve_sin_respuesta_escrita(contexto, gestion):
    conjunto, _, cliente_residente = contexto
    secretaria, administracion = gestion
    caso = abrir(cliente_residente)
    accion(secretaria, caso, "redirigir")

    vacia = accion(administracion, caso, "responder", respuesta="   ")
    sin_campo = accion(administracion, caso, "responder")

    assert vacia.status_code == 400 and "respuesta" in vacia.json()
    assert sin_campo.status_code == 400
    with usar_conjunto(conjunto.id):
        assert Caso.objects.get(pk=caso["id"]).estado == "REDIRIGIDO"
        with pytest.raises(IntegrityError), transaction.atomic():
            Caso.objects.filter(pk=caso["id"]).update(estado="RESUELTO")


def test_administracion_responde_un_caso_redirigido_y_queda_resuelto(contexto, gestion):
    conjunto, _, cliente_residente = contexto
    secretaria, administracion = gestion
    caso = abrir(cliente_residente)
    accion(secretaria, caso, "redirigir")

    respuesta = accion(administracion, caso, "responder", respuesta="El plomero va mañana a las 8.")
    repetida = accion(administracion, caso, "responder", respuesta="Otra respuesta.")
    rechazo = accion(administracion, caso, "rechazar", motivo="Cambio de opinión.")

    assert respuesta.status_code == 200
    assert (respuesta.json()["estado"], respuesta.json()["respuesta"]) == ("RESUELTO", "El plomero va mañana a las 8.")
    assert respuesta.json()["cerrado_por"] == "Ana Gómez" and respuesta.json()["cerrado_en"]
    assert (repetida.status_code, rechazo.status_code) == (409, 409)
    assert avisos_de(conjunto, caso)[-1] == (
        "Pedro", "caso.resuelto", "Tu caso fue resuelto", "«Fuga de agua». Respuesta: El plomero va mañana a las 8.",
    )
    with usar_conjunto(conjunto.id):
        registro = Registro.objects.get(accion="caso.responder", entidad_id=caso["id"])
    assert registro.antes == {"estado": "REDIRIGIDO"}


def test_administracion_solo_puede_responder_y_rechazar_casos_redirigidos(contexto, gestion):
    conjunto, _, cliente_residente = contexto
    _, administracion = gestion
    resuelto = abrir(cliente_residente)
    rechazado = abrir(cliente_residente, "Ruido", "Hay ruidos fuera de horario.")

    respuesta = accion(administracion, resuelto, "responder", respuesta="Ya se habló con el vecino.")
    sin_motivo = accion(administracion, rechazado, "rechazar", motivo="  ")
    rechazo = accion(administracion, rechazado, "rechazar", motivo="No es un asunto de convivencia.")

    assert respuesta.status_code == 409
    assert sin_motivo.status_code == 400
    assert rechazo.status_code == 409
    with usar_conjunto(conjunto.id):
        assert Caso.objects.get(pk=resuelto["id"]).estado == "ABIERTO"
        assert Caso.objects.get(pk=rechazado["id"]).estado == "ABIERTO"


def test_la_prioridad_urgente_exige_justificacion_y_queda_en_auditoria(contexto, gestion):
    conjunto, _, cliente_residente = contexto
    secretaria, administracion = gestion
    caso = abrir(cliente_residente)

    sin_justificar = accion(secretaria, caso, "prioridad", prioridad="URGENTE")
    urgente = accion(secretaria, caso, "prioridad", prioridad="URGENTE", justificacion="Se está inundando el sótano.")
    baja = accion(administracion, caso, "prioridad", prioridad="BAJA", justificacion="Ya no aplica.")
    del_residente = accion(cliente_residente, caso, "prioridad", prioridad="URGENTE", justificacion="Es mi caso.")

    assert sin_justificar.status_code == 400 and "justificacion" in sin_justificar.json()
    assert (urgente.json()["prioridad"], urgente.json()["justificacion_prioridad"]) == (
        "URGENTE", "Se está inundando el sótano."
    )
    assert (baja.json()["prioridad"], baja.json()["justificacion_prioridad"]) == ("BAJA", "")
    assert del_residente.status_code == 403
    with usar_conjunto(conjunto.id):
        cambios = list(Registro.objects.filter(accion="caso.priorizar").order_by("creado_en"))
        with pytest.raises(IntegrityError), transaction.atomic():
            Caso.objects.filter(pk=caso["id"]).update(prioridad="URGENTE")
    assert [(c.antes["prioridad"], c.despues["prioridad"]) for c in cambios] == [("NORMAL", "URGENTE"), ("URGENTE", "BAJA")]
    # Cambiar la prioridad no avisa al residente ni cambia el estado.
    assert avisos_de(conjunto, caso) == []
    assert baja.json()["estado"] == "ABIERTO"


def test_la_bandeja_ordena_por_prioridad_y_luego_por_antiguedad(contexto, gestion):
    _, _, cliente_residente = contexto
    secretaria, administracion = gestion
    primero = abrir(cliente_residente, "Primero", "El más antiguo.")
    segundo = abrir(cliente_residente, "Segundo", "Llegó después.")
    tercero = abrir(cliente_residente, "Tercero", "El más reciente.")
    accion(secretaria, tercero, "prioridad", prioridad="ALTA")
    accion(secretaria, segundo, "prioridad", prioridad="URGENTE", justificacion="Revisión urgente por riesgo de seguridad.")
    accion(secretaria, primero, "redirigir")
    accion(administracion, primero, "responder", respuesta="Listo.")

    def orden(consulta=""):
        return [caso["titulo"] for caso in secretaria.get(f"/casos/{consulta}").json()]

    # Los abiertos primero; entre ellos la prioridad y, a igual prioridad, el que más lleva esperando.
    assert orden() == ["Segundo", "Tercero", "Primero"]
    assert orden("?ver=abiertos") == ["Segundo", "Tercero"]
    # La vista por antigüedad ignora la prioridad por completo.
    assert orden("?ver=abiertos&orden=antiguedad") == ["Segundo", "Tercero"]
    assert secretaria.get("/casos/?orden=azar").status_code == 400
    assert accion(secretaria, primero, "prioridad", prioridad="ALTA").status_code == 409
    assert secretaria.get(f"/casos/{segundo['id']}/").json()["prioridad"] == "URGENTE"


def test_cada_cambio_de_estado_avisa_por_la_aplicacion_y_por_correo(
    contexto, gestion, mailoutbox, django_capture_on_commit_callbacks
):
    conjunto, _, cliente_residente = contexto
    secretaria, administracion = gestion
    caso = abrir(cliente_residente)

    with django_capture_on_commit_callbacks(execute=True):
        accion(secretaria, caso, "tomar")
    with django_capture_on_commit_callbacks(execute=True):
        accion(secretaria, caso, "redirigir")
    with django_capture_on_commit_callbacks(execute=True):
        accion(administracion, caso, "responder", respuesta="Resuelto con el contratista.")

    assert [aviso[1] for aviso in avisos_de(conjunto, caso)] == ["caso.en_revision", "caso.redirigido", "caso.resuelto"]
    assert [correo.to for correo in mailoutbox] == [["vecino@torres.com"]] * 3
    assert "Tu caso fue resuelto" in mailoutbox[-1].subject
    assert "María" not in mailoutbox[-1].body and "Ana" not in mailoutbox[-1].body


def test_superusuario_ve_casos_abiertos_rechazados_y_redirigidos(contexto, gestion):
    conjunto, residente, cliente_residente = contexto
    secretaria, _ = gestion
    abierto = abrir(cliente_residente, "Abierto", "Pendiente")
    rechazado = abrir(cliente_residente, "Rechazado", "Con motivo")
    redirigido = abrir(cliente_residente, "Redirigido", "Enviado a administración")
    accion(secretaria, rechazado, "descartar", causal="INFORMACION_INSUFICIENTE", motivo="No contiene información suficiente.")
    accion(secretaria, redirigido, "redirigir")

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
