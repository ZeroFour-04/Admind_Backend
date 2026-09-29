"""Pruebas de HU-25: anuncios con alcance de conjunto o de vivienda."""
import pytest
from rest_framework.test import APIClient

from apps.anuncios.models import Anuncio
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


def avisados(conjunto, anuncio_id):
    with usar_conjunto(conjunto.id):
        return sorted(n.persona.nombres for n in Notificacion.objects.filter(referencia=anuncio_id))


def anuncios_de(conjunto):
    with usar_conjunto(conjunto.id):
        return list(Anuncio.objects.all())


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
