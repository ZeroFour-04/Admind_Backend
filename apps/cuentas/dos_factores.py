"""Segundo factor TOTP (HU-02), con django-otp como pide el maestro §7.1. No sabe nada de HTTP.

Se exige a todo usuario con algún permiso sensible, en cualquiera de sus conjuntos. La marca de
verificado vive en la sesión (`TokenDeSesion`): cada ingreso nuevo vuelve a pedir el código.
"""
import base64
import re

import qrcode
import qrcode.image.svg
from django.db import transaction
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.permisos.servicios import tiene_permisos_sensibles

CANTIDAD_DE_CODIGOS_DE_RESPALDO = 10
CODIGO_DE_LA_APLICACION = re.compile(r"^\d{6}$")


class CodigoInvalido(Exception):
    """Mal escrito, vencido, ya usado o demasiados intentos seguidos. A propósito no dice cuál."""


class YaConfigurado(Exception):
    """El usuario ya tiene un segundo factor confirmado."""


class SinConfigurar(Exception):
    """Todavía no hay un segundo factor que confirmar o verificar."""


def requiere(usuario):
    return tiene_permisos_sensibles(usuario.persona)


def dispositivo(usuario, confirmado=True):
    return TOTPDevice.objects.filter(user=usuario, confirmed=confirmado).first()


def pendiente(sesion):
    """Si esta sesión todavía no puede operar porque le falta el segundo factor."""
    return not sesion.dos_factores_verificado and requiere(sesion.usuario)


def estado(sesion):
    return {
        "requerido": requiere(sesion.usuario),
        "configurado": dispositivo(sesion.usuario) is not None,
        "verificado": sesion.dos_factores_verificado,
    }


def iniciar_configuracion(sesion):
    """Crea un secreto nuevo sin confirmar y devuelve lo que la persona escanea con su aplicación."""
    usuario = sesion.usuario
    if dispositivo(usuario) is not None:
        raise YaConfigurado()
    with transaction.atomic():
        # Si abandonó una configuración anterior, ese secreto ya no sirve.
        TOTPDevice.objects.filter(user=usuario, confirmed=False).delete()
        nuevo = TOTPDevice.objects.create(user=usuario, name="AdMind", confirmed=False)
    return {
        "clave": base64.b32encode(nuevo.bin_key).decode(),
        "enlace": nuevo.config_url,
        "qr": imagen_qr(nuevo.config_url),
    }


def imagen_qr(texto):
    """El QR como imagen SVG lista para un `<img src>`. SVG, para no depender de Pillow."""
    imagen = qrcode.make(texto, image_factory=qrcode.image.svg.SvgPathImage)
    return "data:image/svg+xml;base64," + base64.b64encode(imagen.to_string()).decode()


def confirmar_configuracion(sesion, codigo):
    """Con el primer código correcto el secreto queda confirmado y nacen los códigos de respaldo.

    Devuelve los códigos de respaldo: es la única vez que se muestran.
    """
    usuario = sesion.usuario
    if dispositivo(usuario) is not None:
        raise YaConfigurado()
    por_confirmar = dispositivo(usuario, confirmado=False)
    if por_confirmar is None:
        raise SinConfigurar()
    if not por_confirmar.verify_token(limpiar(codigo)):
        raise CodigoInvalido()
    with transaction.atomic():
        por_confirmar.confirmed = True
        por_confirmar.save(update_fields=["confirmed"])
        codigos = nuevos_codigos_de_respaldo(usuario)
        marcar_verificada(sesion)
    return codigos


def nuevos_codigos_de_respaldo(usuario):
    StaticDevice.objects.filter(user=usuario).delete()
    respaldo = StaticDevice.objects.create(user=usuario, name="Códigos de respaldo", confirmed=True)
    codigos = [StaticToken.random_token() for _ in range(CANTIDAD_DE_CODIGOS_DE_RESPALDO)]
    StaticToken.objects.bulk_create([StaticToken(device=respaldo, token=codigo) for codigo in codigos])
    return codigos


def verificar(sesion, codigo):
    """Un código de la aplicación o uno de respaldo. El de respaldo se gasta al usarlo."""
    usuario = sesion.usuario
    totp = dispositivo(usuario)
    if totp is None:
        raise SinConfigurar()
    codigo = limpiar(codigo)
    # Se prueba solo contra el dispositivo que corresponde al formato: un intento fallido
    # frena los siguientes, y un código de respaldo no debe frenar la aplicación.
    if CODIGO_DE_LA_APLICACION.match(codigo):
        valido = totp.verify_token(codigo)
    else:
        respaldo = StaticDevice.objects.filter(user=usuario, confirmed=True).first()
        valido = respaldo is not None and respaldo.verify_token(codigo.lower())
    if not valido:
        raise CodigoInvalido()
    marcar_verificada(sesion)


def limpiar(codigo):
    return (codigo or "").replace(" ", "").replace("-", "").strip()


def marcar_verificada(sesion):
    sesion.dos_factores_verificado = True
    sesion.save(update_fields=["dos_factores_verificado"])
