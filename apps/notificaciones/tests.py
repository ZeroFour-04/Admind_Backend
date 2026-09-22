"""Pruebas del canal de notificaciones: bandeja en la aplicación y correo (maestro §3.1)."""
import uuid
from unittest import mock

import pytest
from rest_framework.test import APIClient

from apps.comun.aislamiento.contexto import usar_conjunto
from apps.conjuntos.models import Conjunto
from apps.cuentas.models import TokenDeSesion, Usuario
from apps.notificaciones.canal import Aviso, notificar
from apps.notificaciones.models import Notificacion
from apps.permisos.catalogo import Rol
from apps.permisos.models import Asignacion
from apps.personas.models import Persona, TipoDocumento

pytestmark = pytest.mark.django_db

CONTRASENA = "una-clave-larga-2026"


def crear_persona(nombres, correo=None):
    persona = Persona.objects.create(
        tipo_documento=TipoDocumento.CC,
        numero_documento=str(Persona.objects.count() + 1023456789),
        nombres=nombres,
        apellidos="Gómez",
    )
    if correo:
        Usuario.objects.create_user(correo, CONTRASENA, persona)
    return persona


@pytest.fixture
def torres():
    return Conjunto.objects.create(nombre="Torres del Río")


@pytest.fixture
def aviso():
    return Aviso("Corte de agua", "El jueves de 8 a 2.", origen="anuncio", referencia=uuid.uuid4())


def test_cada_persona_recibe_el_aviso_en_su_bandeja(torres, aviso):
    marta, pedro = crear_persona("Marta"), crear_persona("Pedro")

    with usar_conjunto(torres.id):
        notificar(aviso, [marta.id, pedro.id])
        assert sorted(n.persona.nombres for n in Notificacion.objects.all()) == ["Marta", "Pedro"]


def test_el_mismo_hecho_no_avisa_dos_veces(torres, aviso):
    marta = crear_persona("Marta")

    with usar_conjunto(torres.id):
        notificar(aviso, [marta.id])
        assert notificar(aviso, [marta.id]) == []
        assert Notificacion.objects.count() == 1


def test_llega_un_correo_por_persona_y_solo_a_cuentas_que_pueden_entrar(
    torres, aviso, mailoutbox, django_capture_on_commit_callbacks
):
    marta = crear_persona("Marta", "marta@correo.com")
    pedro = crear_persona("Pedro", "pedro@correo.com")
    sin_cuenta = crear_persona("Ana")
    desactivada = crear_persona("Luis", "luis@correo.com")
    Persona.objects.filter(pk=desactivada.pk).update(activo=False)

    with usar_conjunto(torres.id), django_capture_on_commit_callbacks(execute=True):
        notificar(aviso, [marta.id, pedro.id, sin_cuenta.id, desactivada.id])

    assert sorted(correo.to[0] for correo in mailoutbox) == ["marta@correo.com", "pedro@correo.com"]
    assert all(len(correo.to) == 1 for correo in mailoutbox)
    assert mailoutbox[0].subject == "AdMind · Torres del Río: Corte de agua"
    # La bandeja sí la tienen todos: quien no tiene cuenta la verá si algún día la tiene.
    with usar_conjunto(torres.id):
        assert Notificacion.objects.count() == 4


def test_si_falla_el_correo_el_aviso_queda_en_la_bandeja(torres, aviso, django_capture_on_commit_callbacks):
    marta = crear_persona("Marta", "marta@correo.com")

    with mock.patch("apps.notificaciones.canal.send_mass_mail", side_effect=OSError("SMTP caído")):
        with usar_conjunto(torres.id), django_capture_on_commit_callbacks(execute=True):
            notificar(aviso, [marta.id])

    with usar_conjunto(torres.id):
        assert Notificacion.objects.filter(persona=marta).exists()


def test_la_bandeja_muestra_solo_los_avisos_propios_del_conjunto_activo(torres, aviso):
    mirador = Conjunto.objects.create(nombre="Mirador")
    marta = crear_persona("Marta", "marta@correo.com")
    pedro = crear_persona("Pedro")
    Asignacion.objects.create(persona=marta, rol=Rol.RESIDENTE, conjunto=torres)
    with usar_conjunto(torres.id):
        notificar(aviso, [marta.id, pedro.id])
    with usar_conjunto(mirador.id):
        notificar(Aviso("De Mirador", "", origen="anuncio", referencia=uuid.uuid4()), [marta.id])
    cliente = APIClient()
    token = cliente.post("/auth/login/", {"correo": "marta@correo.com", "contrasena": CONTRASENA}, format="json")
    cliente.credentials(HTTP_AUTHORIZATION=f"Token {token.json()['token']}")
    TokenDeSesion.objects.update(dos_factores_verificado=True)

    bandeja = cliente.get("/notificaciones/").json()

    assert [n["titulo"] for n in bandeja] == ["Corte de agua"]
