"""Reglas de entrada a la API. No saben nada de HTTP: eso es de las vistas."""
import hashlib
import secrets

from django.conf import settings
from django.contrib.auth import authenticate
from django.utils import timezone

from apps.cuentas.models import TokenDeSesion


class CredencialesInvalidas(Exception):
    """Correo o contraseña incorrectos, o cuenta sin acceso. A propósito no dice cuál (HU-01)."""


def huella_de(token):
    return hashlib.sha256(token.encode()).hexdigest()


def puede_entrar(usuario):
    # Desactivar la persona también corta el acceso (maestro §5.11).
    return usuario.is_active and usuario.persona.activo


def iniciar_sesion(correo, contrasena):
    usuario = authenticate(username=correo, password=contrasena)
    if usuario is None or not puede_entrar(usuario):
        raise CredencialesInvalidas()

    token = secrets.token_urlsafe(32)
    sesion = TokenDeSesion.objects.create(
        usuario=usuario,
        huella=huella_de(token),
        vence_en=timezone.now() + settings.DURACION_TOKEN_DE_SESION,
    )
    return token, sesion


def sesion_vigente(token):
    sesion = TokenDeSesion.objects.vigente(huella_de(token))
    if sesion is None or not puede_entrar(sesion.usuario):
        return None
    return sesion


def cerrar_sesion(sesion):
    sesion.delete()
