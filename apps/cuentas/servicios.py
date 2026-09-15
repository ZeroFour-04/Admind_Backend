"""Reglas de entrada a la API. No saben nada de HTTP: eso es de las vistas."""
import hashlib
import secrets

from django.conf import settings
from django.contrib.auth import authenticate
from django.utils import timezone

from apps.cuentas.models import TokenDeSesion
from apps.permisos.servicios import conjuntos_disponibles, puede_operar_en


class CredencialesInvalidas(Exception):
    """Correo o contraseña incorrectos, o cuenta sin acceso. A propósito no dice cuál (HU-01)."""


class ConjuntoNoDisponible(Exception):
    """El conjunto no existe, está desactivado o la persona no tiene asignación vigente ahí."""


def huella_de(token):
    return hashlib.sha256(token.encode()).hexdigest()


def puede_entrar(usuario):
    # Desactivar la persona también corta el acceso (maestro §5.11).
    return usuario.is_active and usuario.persona.activo


def iniciar_sesion(correo, contrasena):
    usuario = authenticate(username=correo, password=contrasena)
    if usuario is None or not puede_entrar(usuario):
        raise CredencialesInvalidas()

    # Con un solo conjunto entra directo, sin pantalla de selección (HU-26).
    disponibles = list(conjuntos_disponibles(usuario.persona)[:2])
    token = secrets.token_urlsafe(32)
    sesion = TokenDeSesion.objects.create(
        usuario=usuario,
        huella=huella_de(token),
        conjunto_activo=disponibles[0] if len(disponibles) == 1 else None,
        vence_en=timezone.now() + settings.DURACION_TOKEN_DE_SESION,
    )
    return token, sesion


def sesion_vigente(token):
    sesion = TokenDeSesion.objects.vigente(huella_de(token))
    if sesion is None or not puede_entrar(sesion.usuario):
        return None

    # Si le retiraron el rol o desactivaron el conjunto, pierde el conjunto activo de inmediato.
    if sesion.conjunto_activo_id and not puede_operar_en(sesion.usuario.persona, sesion.conjunto_activo_id):
        TokenDeSesion.objects.filter(pk=sesion.pk).update(conjunto_activo=None)
        sesion.conjunto_activo = None
    return sesion


def elegir_conjunto(sesion, conjunto_id):
    if not puede_operar_en(sesion.usuario.persona, conjunto_id):
        raise ConjuntoNoDisponible()
    sesion.conjunto_activo_id = conjunto_id
    sesion.save(update_fields=["conjunto_activo"])
    return sesion


def cerrar_sesion(sesion):
    sesion.delete()
