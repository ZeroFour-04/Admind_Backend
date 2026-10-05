"""Pruebas de HU-25: anuncios con alcance de conjunto o de vivienda."""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.anuncios import servicios
from apps.anuncios.models import MAXIMO_DE_FOTOS, Anuncio, FotoDeAnuncio
from apps.comun.aislamiento.contexto import usar_conjunto
from apps.conjuntos.models import Conjunto
from apps.cuentas.models import TokenDeSesion, Usuario
from apps.notificaciones.models import Notificacion
from apps.permisos.catalogo import PERMISOS_POR_ROL, Rol
from apps.permisos.models import Asignacion
from apps.personas.models import Persona, TipoDocumento
from apps.unidades.models import TipoVinculo, Unidad, VinculoUnidad

pytestmark = pytest.mark.django_db

CONTRASENA = "una-clave-larga-2026"

# Para una foto basta la firma del formato: la API no lee el resto de la imagen.
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
WEBP = b"RIFF\x40\x00\x00\x00WEBP" + b"\x00" * 32


def crear_persona(nombres, *roles, correo=None):
    persona = Persona.objects.create(
        tipo_documento=TipoDocumento.CC,
        numero_documento=str(Persona.objects.count() + 1023456789),
        nombres=nombres,
        apellidos="Gómez",
    )
    for rol, conjunto in roles:
        Asignacion.objects.create(persona=persona, rol=rol, conjunto=conjunto)
    if correo:
        Usuario.objects.create_user(correo, CONTRASENA, persona)
    return persona


def cliente_para(correo):
    """Sesión con el segundo factor dado por verificado: su flujo se prueba en cuentas."""
    cliente = APIClient()
    respuesta = cliente.post("/auth/login/", {"correo": correo, "contrasena": CONTRASENA}, format="json")
    cliente.credentials(HTTP_AUTHORIZATION=f"Token {respuesta.json()['token']}")
    TokenDeSesion.objects.filter(usuario__correo=correo).update(dos_factores_verificado=True)
    return cliente


def vincular(persona, unidad, tipo=TipoVinculo.PROPIETARIO, reside=True):
    with usar_conjunto(unidad.conjunto_id):
        VinculoUnidad.objects.create(persona=persona, unidad=unidad, tipo=tipo, reside=reside)


def publicar(cliente, **datos):
    return cliente.post("/anuncios/", {"titulo": "Corte de agua", "cuerpo": "Jueves de 8 a 2.", **datos}, format="json")


def publicar_con_fotos(cliente, *contenidos, tipo="image/png", **datos):
    """Como lo manda un formulario: multipart, con el campo `fotos` repetido."""
    fotos = [
        SimpleUploadedFile(f"foto-{numero}.png", contenido, content_type=tipo)
        for numero, contenido in enumerate(contenidos, start=1)
    ]
    cuerpo = {"titulo": "Corte de agua", "cuerpo": "Jueves de 8 a 2.", "alcance": "conjunto", **datos, "fotos": fotos}
    return cliente.post("/anuncios/", cuerpo, format="multipart")


def avisados(conjunto, anuncio_id):
    with usar_conjunto(conjunto.id):
        return sorted(n.persona.nombres for n in Notificacion.objects.filter(referencia=anuncio_id))


def fotos_de(conjunto):
    with usar_conjunto(conjunto.id):
        return list(FotoDeAnuncio.objects.order_by("anuncio__publicado_en", "orden"))


def sin_rastro_en(conjunto):
    """Ni anuncio, ni foto, ni aviso: la publicación no dejó nada."""
    with usar_conjunto(conjunto.id):
        return not (Anuncio.objects.exists() or FotoDeAnuncio.objects.exists() or Notificacion.objects.exists())


def anuncios_de(conjunto):
    with usar_conjunto(conjunto.id):
        return list(Anuncio.objects.all())


def anuncio_en(conjunto):
    """Un anuncio creado directo en la base, para probar lo que la base guarda de sus fotos."""
    autor = crear_persona("Autora")
    with usar_conjunto(conjunto.id):
        return Anuncio.objects.create(titulo="Corte de agua", cuerpo="Jueves", alcance="conjunto", autor=autor)


@pytest.fixture
def torres():
    return Conjunto.objects.create(nombre="Torres del Río")


@pytest.fixture
def viviendas(torres):
    with usar_conjunto(torres.id):
        return Unidad.objects.create(nombre="Torre 1 – 101"), Unidad.objects.create(nombre="Torre 1 – 102")


@pytest.fixture
def secretaria(torres):
    crear_persona("Sara", (Rol.SECRETARIA, torres), correo="secretaria@torres.com")
    return cliente_para("secretaria@torres.com")


@pytest.fixture
def vecinos(torres, viviendas):
    """En el 101, dueña que no vive ahí y arrendatario. En el 102, un residente."""
    apto_101, apto_102 = viviendas
    marta = crear_persona("Marta", correo="marta@correo.com")  # sin rol en el conjunto
    pedro = crear_persona("Pedro", (Rol.RESIDENTE, torres), correo="pedro@correo.com")
    lucia = crear_persona("Lucía", (Rol.RESIDENTE, torres), correo="lucia@correo.com")
    vincular(marta, apto_101, TipoVinculo.PROPIETARIO, reside=False)
    vincular(pedro, apto_101, TipoVinculo.ARRENDATARIO)
    vincular(lucia, apto_102)
    return marta, pedro, lucia


# Criterios de aceptación


def test_anuncio_al_conjunto_llega_a_toda_persona_con_asignacion_vigente(secretaria, torres, vecinos):
    otro = Conjunto.objects.create(nombre="Mirador")
    crear_persona("Ajeno", (Rol.RESIDENTE, otro))

    respuesta = publicar(secretaria, alcance="conjunto")

    assert respuesta.status_code == 201
    # Marta no tiene asignación en el conjunto: el alcance conjunto va por asignaciones, no por vínculos.
    assert avisados(torres, respuesta.json()["id"]) == ["Lucía", "Pedro", "Sara"]


def test_anuncio_a_una_vivienda_llega_a_sus_vinculos_vigentes_y_a_nadie_mas(secretaria, torres, viviendas, vecinos):
    apto_101, _ = viviendas

    respuesta = publicar(secretaria, alcance="vivienda", unidad=str(apto_101.id))

    assert respuesta.status_code == 201
    assert respuesta.json()["unidad"] == {"id": str(apto_101.id), "nombre": "Torre 1 – 101"}
    assert avisados(torres, respuesta.json()["id"]) == ["Marta", "Pedro"]


def test_no_existe_el_alcance_persona(secretaria, torres, vecinos):
    _, pedro, _ = vecinos

    respuesta = publicar(secretaria, alcance="persona", persona=str(pedro.id))

    assert respuesta.status_code == 400
    assert "alcance" in respuesta.json()
    assert anuncios_de(torres) == []


def test_editar_un_anuncio_publicado_no_vuelve_a_avisar(
    secretaria, torres, vecinos, mailoutbox, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        anuncio = publicar(secretaria, alcance="conjunto").json()
    correos_al_publicar = len(mailoutbox)

    with django_capture_on_commit_callbacks(execute=True):
        respuesta = secretaria.patch(f"/anuncios/{anuncio['id']}/", {"cuerpo": "Mejor el viernes."}, format="json")

    assert respuesta.status_code == 200
    assert respuesta.json()["cuerpo"] == "Mejor el viernes."
    assert respuesta.json()["editado_en"] is not None
    assert correos_al_publicar == 3
    assert len(mailoutbox) == correos_al_publicar
    assert len(avisados(torres, anuncio["id"])) == 3


def test_con_anuncio_publicar_pero_sin_anuncio_dirigir_no_publica_a_una_vivienda(monkeypatch, torres, viviendas):
    # Ningún rol del catálogo tiene uno sin el otro: se simula para probar que van separados.
    monkeypatch.setitem(PERMISOS_POR_ROL, Rol.VIGILANCIA, PERMISOS_POR_ROL[Rol.VIGILANCIA] | {"anuncio.publicar"})
    crear_persona("Carlos", (Rol.VIGILANCIA, torres), correo="vigilancia@torres.com")
    vigilancia = cliente_para("vigilancia@torres.com")
    apto_101, _ = viviendas

    assert publicar(vigilancia, alcance="vivienda", unidad=str(apto_101.id)).status_code == 403
    assert publicar(vigilancia, alcance="conjunto").status_code == 201


# Reglas de la publicación


def test_sin_ningun_permiso_de_anuncios_no_publica(torres, vecinos):
    residente = cliente_para("pedro@correo.com")

    assert publicar(residente, alcance="conjunto").status_code == 403


def test_a_una_vivienda_hay_que_elegirla_y_al_conjunto_no_se_le_pone(secretaria, viviendas):
    apto_101, _ = viviendas

    assert publicar(secretaria, alcance="vivienda").json()["unidad"] == ["Elige la vivienda a la que va el anuncio."]
    assert publicar(secretaria, alcance="conjunto", unidad=str(apto_101.id)).status_code == 400


def test_no_se_dirige_a_una_vivienda_de_otro_conjunto(secretaria):
    mirador = Conjunto.objects.create(nombre="Mirador")
    with usar_conjunto(mirador.id):
        ajena = Unidad.objects.create(nombre="Casa 1")

    respuesta = publicar(secretaria, alcance="vivienda", unidad=str(ajena.id))

    assert respuesta.status_code == 400
    assert respuesta.json()["unidad"] == ["Esa vivienda no existe en este conjunto."]


def test_el_alcance_no_cambia_despues_de_publicar(secretaria, torres, viviendas):
    apto_101, _ = viviendas
    anuncio = publicar(secretaria, alcance="conjunto").json()

    respuesta = secretaria.patch(
        f"/anuncios/{anuncio['id']}/", {"alcance": "vivienda", "unidad": str(apto_101.id)}, format="json"
    )

    assert respuesta.status_code == 400
    assert [anuncio.alcance for anuncio in anuncios_de(torres)] == ["conjunto"]


def test_solo_quien_lo_publico_lo_edita(secretaria, torres):
    anuncio = publicar(secretaria, alcance="conjunto").json()
    crear_persona("Andrés", (Rol.ADMINISTRACION, torres), correo="admin@torres.com")
    admin = cliente_para("admin@torres.com")

    respuesta = admin.patch(f"/anuncios/{anuncio['id']}/", {"titulo": "Otro"}, format="json")

    assert respuesta.status_code == 403
    assert admin.get(f"/anuncios/{anuncio['id']}/").json()["puede_editar"] is False
    assert secretaria.get(f"/anuncios/{anuncio['id']}/").json()["puede_editar"] is True


# Tablón


def test_cada_residente_ve_los_del_conjunto_y_los_de_su_vivienda_nada_mas(secretaria, viviendas, vecinos):
    apto_101, apto_102 = viviendas
    publicar(secretaria, alcance="conjunto", titulo="Piscina cerrada")
    publicar(secretaria, alcance="vivienda", unidad=str(apto_101.id), titulo="Gas en el 101")
    para_el_102 = publicar(secretaria, alcance="vivienda", unidad=str(apto_102.id), titulo="Gas en el 102").json()
    pedro = cliente_para("pedro@correo.com")

    titulos = sorted(anuncio["titulo"] for anuncio in pedro.get("/anuncios/").json())

    assert titulos == ["Gas en el 101", "Piscina cerrada"]
    assert pedro.get(f"/anuncios/{para_el_102['id']}/").status_code == 404
    assert len(secretaria.get("/anuncios/").json()) == 3


# Fotos: lo que guarda la base


def test_la_base_rechaza_dos_fotos_con_el_mismo_orden_en_un_anuncio(torres):
    anuncio = anuncio_en(torres)
    with usar_conjunto(torres.id):
        FotoDeAnuncio.objects.create(anuncio=anuncio, contenido=PNG, tipo="image/png", orden=0)
        with pytest.raises(IntegrityError), transaction.atomic():
            FotoDeAnuncio.objects.create(anuncio=anuncio, contenido=JPG, tipo="image/jpeg", orden=0)


def test_la_base_rechaza_una_foto_mas_alla_del_tope(torres):
    anuncio = anuncio_en(torres)
    with usar_conjunto(torres.id):
        for orden in range(MAXIMO_DE_FOTOS):
            FotoDeAnuncio.objects.create(anuncio=anuncio, contenido=PNG, tipo="image/png", orden=orden)
        with pytest.raises(IntegrityError), transaction.atomic():
            FotoDeAnuncio.objects.create(anuncio=anuncio, contenido=PNG, tipo="image/png", orden=MAXIMO_DE_FOTOS)


def test_la_base_rechaza_una_foto_que_apunta_a_un_anuncio_de_otro_conjunto(torres):
    ajeno = anuncio_en(Conjunto.objects.create(nombre="Mirador"))
    with usar_conjunto(torres.id), pytest.raises(IntegrityError), transaction.atomic():
        FotoDeAnuncio.objects.create(anuncio=ajeno, contenido=PNG, tipo="image/png", orden=0)


# Fotos: publicar


def test_publicar_con_dos_fotos_las_guarda_en_orden_y_responde_sus_ids(secretaria, torres):
    respuesta = publicar_con_fotos(secretaria, PNG, JPG)

    assert respuesta.status_code == 201
    guardadas = fotos_de(torres)
    assert [(bytes(foto.contenido), foto.orden) for foto in guardadas] == [(PNG, 0), (JPG, 1)]
    assert respuesta.json()["fotos"] == [str(foto.id) for foto in guardadas]
    assert secretaria.get("/anuncios/").json()[0]["fotos"] == respuesta.json()["fotos"]


def test_publicar_solo_texto_por_json_sigue_funcionando_y_responde_sin_fotos(secretaria, torres):
    respuesta = publicar(secretaria, alcance="conjunto")

    assert respuesta.status_code == 201
    assert respuesta.json()["fotos"] == []
    assert fotos_de(torres) == []


def test_con_mas_fotos_que_el_tope_no_se_publica_ni_se_avisa(secretaria, torres):
    respuesta = publicar_con_fotos(secretaria, *[PNG] * (MAXIMO_DE_FOTOS + 1))

    assert respuesta.status_code == 400
    assert respuesta.json()["fotos"] == ["Un anuncio lleva hasta 4 fotos."]
    assert sin_rastro_en(torres)


def test_un_archivo_que_no_es_imagen_no_se_publica_ni_se_avisa(secretaria, torres):
    # Un texto con nombre .png y tipo image/png: lo que cuenta es la firma del archivo.
    respuesta = publicar_con_fotos(secretaria, PNG, b"hola, no soy una imagen")

    assert respuesta.status_code == 400
    assert respuesta.json()["fotos"] == ["La foto 2 no es una imagen PNG, JPG o WebP."]
    assert sin_rastro_en(torres)


def test_una_foto_vacia_o_mas_pesada_que_el_tope_se_rechaza(secretaria, torres):
    pesada = PNG + b"\x00" * servicios.TAMANO_MAXIMO_FOTO

    assert publicar_con_fotos(secretaria, pesada).json()["fotos"] == ["La foto 1 pesa más de 5 MB."]
    assert publicar_con_fotos(secretaria, PNG, b"").json()["fotos"] == ["La foto 2 está vacía."]
    assert sin_rastro_en(torres)


@pytest.mark.parametrize(
    ("contenido", "tipo_real"), [(PNG, "image/png"), (JPG, "image/jpeg"), (WEBP, "image/webp")]
)
def test_cada_foto_se_guarda_con_su_tipo_real_aunque_se_declare_otro(secretaria, torres, contenido, tipo_real):
    respuesta = publicar_con_fotos(secretaria, contenido, tipo="text/plain")

    assert respuesta.status_code == 201
    assert [foto.tipo for foto in fotos_de(torres)] == [tipo_real]


def test_el_aviso_de_un_anuncio_con_fotos_dice_cuantas_tiene(
    secretaria, torres, mailoutbox, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        publicar_con_fotos(secretaria, PNG, JPG)
        publicar_con_fotos(secretaria, PNG)
        publicar(secretaria, alcance="conjunto")

    esperados = [
        "Jueves de 8 a 2.\n\nEste anuncio tiene 2 fotos. Míralas en AdMind.",
        "Jueves de 8 a 2.\n\nEste anuncio tiene 1 foto. Mírala en AdMind.",
        "Jueves de 8 a 2.",
    ]
    with usar_conjunto(torres.id):
        assert [aviso.cuerpo for aviso in Notificacion.objects.order_by("creada_en")] == esperados
    assert [correo.body for correo in mailoutbox] == esperados


# Fotos: verlas


def test_quien_ve_el_anuncio_recibe_la_imagen_con_su_tipo(secretaria, vecinos):
    anuncio = publicar_con_fotos(secretaria, JPG).json()
    pedro = cliente_para("pedro@correo.com")

    respuesta = pedro.get(f"/anuncios/{anuncio['id']}/fotos/{anuncio['fotos'][0]}/")

    assert respuesta.status_code == 200
    assert respuesta.content == JPG
    assert respuesta["Content-Type"] == "image/jpeg"


def test_la_foto_de_un_anuncio_dirigido_no_se_entrega_al_vecino(secretaria, viviendas, vecinos):
    _, apto_102 = viviendas
    anuncio = publicar_con_fotos(secretaria, PNG, alcance="vivienda", unidad=str(apto_102.id)).json()
    url = f"/anuncios/{anuncio['id']}/fotos/{anuncio['fotos'][0]}/"

    # Pedro vive en el 101 y Lucía en el 102.
    assert cliente_para("pedro@correo.com").get(url).status_code == 404
    assert cliente_para("lucia@correo.com").get(url).content == PNG


def test_una_foto_no_se_entrega_con_el_id_de_otro_anuncio(secretaria):
    con_foto = publicar_con_fotos(secretaria, PNG).json()
    otro = publicar(secretaria, alcance="conjunto").json()

    respuesta = secretaria.get(f"/anuncios/{otro['id']}/fotos/{con_foto['fotos'][0]}/")

    assert respuesta.status_code == 404


def test_las_fotos_no_cambian_despues_de_publicar(secretaria, torres):
    anuncio = publicar_con_fotos(secretaria, PNG).json()
    url = f"/anuncios/{anuncio['id']}/"
    otra = SimpleUploadedFile("otra.jpg", JPG, content_type="image/jpeg")

    con_archivo = secretaria.patch(url, {"cuerpo": "Mejor el viernes.", "fotos": [otra]}, format="multipart")
    sin_fotos = secretaria.patch(url, {"fotos": []}, format="json")

    mensaje = ["Las fotos de un anuncio no cambian después de publicarlo."]
    assert (con_archivo.status_code, con_archivo.json()["non_field_errors"]) == (400, mensaje)
    assert (sin_fotos.status_code, sin_fotos.json()["non_field_errors"]) == (400, mensaje)
    assert [bytes(foto.contenido) for foto in fotos_de(torres)] == [PNG]
    assert secretaria.get(url).json()["cuerpo"] == "Jueves de 8 a 2."


def test_leer_o_publicar_un_anuncio_no_trae_de_la_base_el_contenido_de_las_fotos(secretaria):
    with CaptureQueriesContext(connection) as consultas:
        anuncio = publicar_con_fotos(secretaria, PNG, JPG).json()
        tablon = secretaria.get("/anuncios/").json()
        detalle = secretaria.get(f"/anuncios/{anuncio['id']}/").json()

    assert len(anuncio["fotos"]) == len(tablon[0]["fotos"]) == len(detalle["fotos"]) == 2
    lecturas = [consulta["sql"] for consulta in consultas if consulta["sql"].startswith("SELECT")]
    assert any('"anuncios_fotodeanuncio"' in sql for sql in lecturas)
    assert not any('"anuncios_fotodeanuncio"."contenido"' in sql for sql in lecturas)
