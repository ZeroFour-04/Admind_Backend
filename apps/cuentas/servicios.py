"""Reglas de entrada a la API y de las cuentas. No saben nada de HTTP: eso es de las vistas."""
import hashlib
import secrets
import uuid

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from apps.cuentas.models import TokenDeSesion, Usuario
from apps.permisos.models import Asignacion
from apps.permisos.servicios import conjuntos_disponibles, puede_operar_en
from apps.personas.models import Persona


class CredencialesInvalidas(Exception):
    """Correo o contraseña incorrectos, o cuenta sin acceso. A propósito no dice cuál (HU-01)."""


class ConjuntoNoDisponible(Exception):
    """El conjunto no existe, está desactivado o la persona no tiene asignación vigente ahí."""


class PersonaYaExiste(Exception):
    """Ya hay una persona con ese tipo y número de documento (HU-04)."""


class EnlaceInvalido(Exception):
    """El enlace de recuperación no existe, ya se usó o venció (HU-01)."""


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


# Usuarios del conjunto activo


def usuarios_del_conjunto(conjunto_id):
    """Cuentas de las personas con algún rol vigente en el conjunto. Las de otros conjuntos no aparecen (HU-05)."""
    en_el_conjunto = Asignacion.objects.vigentes().filter(conjunto_id=conjunto_id)
    return (
        Usuario.objects.select_related("persona")
        .filter(persona__in=en_el_conjunto.values("persona_id"))
        .prefetch_related(
            Prefetch("persona__asignaciones", queryset=en_el_conjunto, to_attr="asignaciones_en_conjunto")
        )
        .order_by("persona__apellidos", "persona__nombres")
    )


def registrar_usuario(conjunto_id, *, tipo_documento, numero_documento, nombres, apellidos, correo,
                      contrasena, rol, telefono=""):
    """Crea la persona, su cuenta y su rol en el conjunto activo, todo o nada."""
    try:
        with transaction.atomic():
            persona = Persona.objects.create(
                tipo_documento=tipo_documento,
                numero_documento=numero_documento,
                nombres=nombres,
                apellidos=apellidos,
                telefono=telefono,
            )
            usuario = Usuario.objects.create_user(correo=correo, password=contrasena, persona=persona)
            Asignacion.objects.create(persona=persona, rol=rol, conjunto_id=conjunto_id)
    except IntegrityError as error:
        # Si dos altas con el mismo documento llegan a la vez, la base decide (HU-04).
        if "persona_documento_unico" in str(error):
            raise PersonaYaExiste() from error
        raise
    return usuario


# Recuperación de contraseña (HU-01)


def solicitar_recuperacion(correo):
    """Envía el enlace si la cuenta existe y puede entrar. Si no, no hace nada y no lo dice."""
    usuario = Usuario.objects.select_related("persona").filter(correo=correo.strip().lower()).first()
    if usuario is None or not puede_entrar(usuario):
        return
    uid = urlsafe_base64_encode(force_bytes(usuario.pk))
    token = default_token_generator.make_token(usuario)
    enlace = f"{settings.ADMIND_FRONT_URL}/restablecer-contrasena/{uid}/{token}/"
    minutos = settings.PASSWORD_RESET_TIMEOUT // 60
    send_mail(
        subject="AdMind: restablece tu contraseña",
        message=(
            f"Hola, {usuario.persona.nombres}.\n\n"
            f"Pediste restablecer la contraseña de AdMind. Abre este enlace para elegir una nueva:\n\n"
            f"{enlace}\n\n"
            f"El enlace sirve una sola vez y vence en {minutos} minutos. "
            f"Si no lo pediste, ignora este correo: tu contraseña sigue igual."
        ),
        from_email=None,
        recipient_list=[usuario.correo],
    )


def restablecer_contrasena(uid, token, contrasena):
    """Cambia la contraseña con un enlace válido y cierra las sesiones abiertas.

    El enlace es de un solo uso porque el token depende de la contraseña: al cambiarla, deja
    de servir. Si la contraseña nueva no cumple las reglas, `validate_password` lo dice.
    """
    usuario = usuario_del_enlace(uid)
    if usuario is None or not puede_entrar(usuario) or not default_token_generator.check_token(usuario, token):
        raise EnlaceInvalido()
    validate_password(contrasena, usuario)
    with transaction.atomic():
        usuario.set_password(contrasena)
        usuario.save(update_fields=["password"])
        TokenDeSesion.objects.filter(usuario=usuario).delete()


def usuario_del_enlace(uid):
    try:
        pk = uuid.UUID(urlsafe_base64_decode(uid).decode())
    except (ValueError, TypeError, UnicodeDecodeError):
        return None
    return Usuario.objects.select_related("persona").filter(pk=pk).first()
