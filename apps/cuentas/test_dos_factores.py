"""Pruebas de HU-02: segundo factor TOTP para quien tiene permisos sensibles."""
import time

import pytest
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django_otp.oath import TOTP
from django_otp.plugins.otp_static.models import StaticDevice
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


# Sin la aplicación ni los códigos de respaldo: se quita por correo


def pedir_enlace(cliente):
    return cliente.post("/auth/dos-factores/restablecer/")


def enlace_del_correo(bandeja):
    enlace = next(linea for linea in bandeja[-1].body.splitlines() if "/segundo-factor/restablecer/" in linea)
    uid, token = enlace.rstrip("/").split("/")[-2:]
    return uid, token


def quitar(uid, token):
    # Sin sesión: el enlace del correo se puede abrir en otro equipo.
    return APIClient().post("/auth/dos-factores/restablecer/confirmar/", {"uid": uid, "token": token}, format="json")


def test_quien_perdio_la_aplicacion_recibe_un_enlace_en_el_correo_de_su_cuenta(usuario, torres, mailoutbox):
    asignar(usuario, Rol.ADMINISTRACION, torres)
    configurar(entrar()[0])
    # Sesión nueva: la contraseña está bien y el segundo factor sigue sin verificar.
    cliente, _ = entrar()

    respuesta = pedir_enlace(cliente)

    assert respuesta.status_code == 202
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["laura@correo.com"]
    assert "/segundo-factor/restablecer/" in mailoutbox[0].body


def test_sin_haber_entrado_con_la_contrasena_no_se_puede_pedir_el_enlace(usuario, torres, mailoutbox):
    asignar(usuario, Rol.ADMINISTRACION, torres)
    configurar(entrar()[0])

    assert pedir_enlace(APIClient()).status_code == 401
    assert mailoutbox == []


def test_sin_segundo_factor_configurado_no_hay_enlace_que_pedir(usuario, torres, mailoutbox):
    asignar(usuario, Rol.ADMINISTRACION, torres)
    cliente, _ = entrar()

    assert pedir_enlace(cliente).status_code == 400
    assert mailoutbox == []


def test_con_el_enlace_se_quita_el_segundo_factor_y_se_cierran_las_sesiones(usuario, torres, mailoutbox):
    asignar(usuario, Rol.ADMINISTRACION, torres)
    configurar(entrar()[0])
    pedir_enlace(entrar()[0])

    respuesta = quitar(*enlace_del_correo(mailoutbox))

    assert respuesta.status_code == 204
    assert not TOTPDevice.objects.exists()
    assert not StaticDevice.objects.exists()
    assert not TokenDeSesion.objects.exists()
    # Al volver a entrar tiene que configurar uno nuevo antes de seguir.
    cliente, sesion = entrar()
    assert sesion["dos_factores"] == {"requerido": True, "configurado": False, "verificado": False}
    assert cliente.get("/auth/conjuntos/").status_code == 403
    assert cliente.post("/auth/dos-factores/configurar/").status_code == 200


def test_el_enlace_para_quitarlo_sirve_una_sola_vez(usuario, torres, mailoutbox):
    asignar(usuario, Rol.ADMINISTRACION, torres)
    configurar(entrar()[0])
    pedir_enlace(entrar()[0])
    uid, token = enlace_del_correo(mailoutbox)
    assert quitar(uid, token).status_code == 204
    # Ya configuró uno nuevo: el enlace viejo no lo puede quitar.
    configurar(entrar()[0])

    assert quitar(uid, token).status_code == 400
    assert TOTPDevice.objects.filter(confirmed=True).exists()


def test_el_enlace_para_quitarlo_vencido_no_sirve(usuario, torres, mailoutbox, settings):
    asignar(usuario, Rol.ADMINISTRACION, torres)
    configurar(entrar()[0])
    pedir_enlace(entrar()[0])
    uid, token = enlace_del_correo(mailoutbox)
    settings.PASSWORD_RESET_TIMEOUT = -1

    assert quitar(uid, token).status_code == 400
    assert TOTPDevice.objects.exists()


def test_un_enlace_de_recuperar_la_contrasena_no_quita_el_segundo_factor(usuario, torres):
    asignar(usuario, Rol.ADMINISTRACION, torres)
    configurar(entrar()[0])
    uid = urlsafe_base64_encode(force_bytes(usuario.pk))

    respuesta = quitar(uid, default_token_generator.make_token(usuario))

    assert respuesta.status_code == 400
    assert TOTPDevice.objects.exists()


def test_el_cuarto_enlace_en_una_hora_para_la_misma_cuenta_se_rechaza(usuario, torres, mailoutbox):
    asignar(usuario, Rol.ADMINISTRACION, torres)
    configurar(entrar()[0])
    cliente, _ = entrar()
    for _ in range(3):
        assert pedir_enlace(cliente).status_code == 202

    cuarto = pedir_enlace(cliente)

    assert cuarto.status_code == 429
    assert cuarto.json() == {
        "detail": "Se pidieron demasiados enlaces para esta cuenta. Espera una hora e intenta de nuevo."
    }
    assert len(mailoutbox) == 3
