"""Pruebas de HU-02: segundo factor TOTP para quien tiene permisos sensibles."""
import time

import pytest
from django_otp.oath import TOTP
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework.test import APIClient

from apps.conjuntos.models import Conjunto
from apps.cuentas.models import TokenDeSesion, Usuario
from apps.permisos.catalogo import Rol
from apps.permisos.models import Asignacion
from apps.personas.models import Persona, TipoDocumento

pytestmark = pytest.mark.django_db

CONTRASENA = "una-clave-larga-2026"


@pytest.fixture(autouse=True)
def sin_espera_entre_intentos(settings):
    # Tras un código errado, django-otp hace esperar antes del siguiente intento. En las pruebas
    # que encadenan intentos esa espera estorba; la que prueba el freno la vuelve a poner.
    settings.OTP_TOTP_THROTTLE_FACTOR = 0
    settings.OTP_STATIC_THROTTLE_FACTOR = 0


@pytest.fixture
def usuario():
    persona = Persona.objects.create(
        tipo_documento=TipoDocumento.CC, numero_documento="1023456789", nombres="Laura", apellidos="Gómez"
    )
    return Usuario.objects.create_user("laura@correo.com", CONTRASENA, persona)


@pytest.fixture
def torres():
    return Conjunto.objects.create(nombre="Torres del Río")


def asignar(usuario, rol, conjunto=None):
    Asignacion.objects.create(persona=usuario.persona, rol=rol, conjunto=conjunto)


def entrar():
    cliente = APIClient()
    respuesta = cliente.post("/auth/login/", {"correo": "laura@correo.com", "contrasena": CONTRASENA}, format="json")
    cliente.credentials(HTTP_AUTHORIZATION=f"Token {respuesta.json()['token']}")
    return cliente, respuesta.json()


def codigo(dispositivo, pasos=0):
    """El código que mostraría la aplicación del celular, `pasos` intervalos de 30 s desde ahora."""
    totp = TOTP(dispositivo.bin_key, dispositivo.step, dispositivo.t0, dispositivo.digits)
    totp.time = time.time() + pasos * dispositivo.step
    return f"{totp.token():0{dispositivo.digits}d}"


def configurar(cliente):
    """Configura el segundo factor completo y devuelve el dispositivo y los códigos de respaldo."""
    cliente.post("/auth/dos-factores/configurar/")
    dispositivo = TOTPDevice.objects.get()
    respuesta = cliente.post("/auth/dos-factores/activar/", {"codigo": codigo(dispositivo)}, format="json")
    dispositivo.refresh_from_db()
    return dispositivo, respuesta.json()["codigos_de_respaldo"]


# Quién lo necesita


def test_residente_no_necesita_segundo_factor(usuario, torres):
    asignar(usuario, Rol.RESIDENTE, torres)

    cliente, sesion = entrar()

    assert sesion["dos_factores"]["requerido"] is False
    assert cliente.get("/auth/conjuntos/").status_code == 200


def test_superusuario_siempre_necesita_segundo_factor(usuario):
    asignar(usuario, Rol.SUPERUSUARIO)

    cliente, sesion = entrar()

    assert sesion["dos_factores"] == {"requerido": True, "configurado": False, "verificado": False}
    assert cliente.get("/auth/conjuntos/").status_code == 403


def test_con_permiso_sensible_y_sin_configurar_no_puede_continuar(usuario, torres):
    asignar(usuario, Rol.ADMINISTRACION, torres)

    cliente, sesion = entrar()

    assert sesion["dos_factores"]["requerido"] is True
    assert cliente.get("/auth/conjuntos/").status_code == 403
    assert cliente.get("/conjuntos/actual/").status_code == 403


def test_sin_segundo_factor_si_puede_cerrar_sesion(usuario, torres):
    asignar(usuario, Rol.ADMINISTRACION, torres)
    cliente, _ = entrar()

    assert cliente.post("/auth/logout/").status_code == 204


# Configurarlo


def test_configurar_entrega_el_qr_y_la_clave_para_la_aplicacion(usuario, torres):
    asignar(usuario, Rol.ADMINISTRACION, torres)
    cliente, _ = entrar()

    respuesta = cliente.post("/auth/dos-factores/configurar/")

    assert respuesta.status_code == 200
    assert respuesta.json()["qr"].startswith("data:image/svg+xml;base64,")
    assert respuesta.json()["enlace"].startswith("otpauth://totp/")
    assert "issuer=AdMind" in respuesta.json()["enlace"]
    assert TOTPDevice.objects.get().confirmed is False


def test_con_el_primer_codigo_correcto_queda_activo_y_entrega_codigos_de_respaldo(usuario, torres):
    asignar(usuario, Rol.ADMINISTRACION, torres)
    cliente, _ = entrar()

    dispositivo, respaldo = configurar(cliente)

    assert dispositivo.confirmed is True
    assert len(respaldo) == 10
    assert cliente.get("/auth/conjuntos/").status_code == 200


def test_codigo_errado_no_activa_el_segundo_factor(usuario, torres):
    asignar(usuario, Rol.ADMINISTRACION, torres)
    cliente, _ = entrar()
    cliente.post("/auth/dos-factores/configurar/")

    respuesta = cliente.post("/auth/dos-factores/activar/", {"codigo": "000000"}, format="json")

    assert respuesta.status_code == 400
    assert TOTPDevice.objects.get().confirmed is False
    assert cliente.get("/auth/conjuntos/").status_code == 403


def test_no_se_puede_configurar_dos_veces(usuario, torres):
    asignar(usuario, Rol.ADMINISTRACION, torres)
    cliente, _ = entrar()
    configurar(cliente)

    assert cliente.post("/auth/dos-factores/configurar/").status_code == 409


# Verificarlo en cada ingreso


def test_cada_ingreso_nuevo_vuelve_a_pedir_el_codigo(usuario, torres):
    asignar(usuario, Rol.ADMINISTRACION, torres)
    dispositivo, _ = configurar(entrar()[0])

    cliente, sesion = entrar()

    assert sesion["dos_factores"] == {"requerido": True, "configurado": True, "verificado": False}
    assert cliente.get("/auth/conjuntos/").status_code == 403


def test_con_un_codigo_valido_accede(usuario, torres):
    asignar(usuario, Rol.ADMINISTRACION, torres)
    dispositivo, _ = configurar(entrar()[0])
    cliente, _ = entrar()

    respuesta = cliente.post("/auth/dos-factores/verificar/", {"codigo": codigo(dispositivo, pasos=1)}, format="json")

    assert respuesta.status_code == 200
    assert respuesta.json()["dos_factores"]["verificado"] is True
    assert cliente.get("/auth/conjuntos/").status_code == 200


def test_un_codigo_repetido_se_rechaza(usuario, torres):
    asignar(usuario, Rol.ADMINISTRACION, torres)
    dispositivo, _ = configurar(entrar()[0])
    usado = codigo(dispositivo, pasos=1)
    primera, _ = entrar()
    primera.post("/auth/dos-factores/verificar/", {"codigo": usado}, format="json")

    segunda, _ = entrar()
    respuesta = segunda.post("/auth/dos-factores/verificar/", {"codigo": usado}, format="json")

    assert respuesta.status_code == 400
    assert segunda.get("/auth/conjuntos/").status_code == 403


def test_un_codigo_vencido_se_rechaza(usuario, torres):
    asignar(usuario, Rol.ADMINISTRACION, torres)
    dispositivo, _ = configurar(entrar()[0])
    cliente, _ = entrar()

    # Hace tres intervalos (1,5 minutos): fuera de la tolerancia de un intervalo.
    respuesta = cliente.post("/auth/dos-factores/verificar/", {"codigo": codigo(dispositivo, pasos=-3)}, format="json")

    assert respuesta.status_code == 400


def test_un_codigo_de_respaldo_sirve_una_sola_vez(usuario, torres):
    asignar(usuario, Rol.ADMINISTRACION, torres)
    _, respaldo = configurar(entrar()[0])
    primera, _ = entrar()
    segunda, _ = entrar()

    assert primera.post("/auth/dos-factores/verificar/", {"codigo": respaldo[0]}, format="json").status_code == 200
    assert segunda.post("/auth/dos-factores/verificar/", {"codigo": respaldo[0]}, format="json").status_code == 400


def test_tras_un_codigo_errado_hay_que_esperar_antes_de_otro_intento(usuario, torres, settings):
    asignar(usuario, Rol.ADMINISTRACION, torres)
    dispositivo, _ = configurar(entrar()[0])
    cliente, _ = entrar()
    settings.OTP_TOTP_THROTTLE_FACTOR = 60

    cliente.post("/auth/dos-factores/verificar/", {"codigo": "000000"}, format="json")
    respuesta = cliente.post("/auth/dos-factores/verificar/", {"codigo": codigo(dispositivo, pasos=1)}, format="json")

    assert respuesta.status_code == 400


def test_la_verificacion_es_de_la_sesion_y_no_de_la_cuenta(usuario, torres):
    asignar(usuario, Rol.ADMINISTRACION, torres)
    configurado, _ = entrar()
    configurar(configurado)

    entrar()

    assert sorted(TokenDeSesion.objects.values_list("dos_factores_verificado", flat=True)) == [False, True]
