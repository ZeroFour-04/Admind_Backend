"""Armado y envío de los correos de AdMind: texto plano más HTML, con el logo incrustado.

Todos los correos de la API pasan por aquí, así se ven iguales: el canal de avisos, la
recuperación de contraseña y el restablecimiento del segundo factor.
"""
import logging
import threading
from email.mime.image import MIMEImage
from functools import cache
from pathlib import Path

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

LOGO = Path(__file__).parent / "recursos" / "logo-marca.png"
# La plantilla base lo referencia como `cid:logo`.
LOGO_CID = "logo"


@cache
def _bytes_del_logo():
    return LOGO.read_bytes()


def armar(asunto, texto, plantilla, contexto, destinatario):
    """Un correo para una persona: `texto` para quien no lee HTML y la plantilla para el resto.

    El logo viaja dentro del mensaje (CID) y no por URL: así se ve aunque el cliente de correo
    bloquee las imágenes remotas y no depende de que el servidor esté publicado.
    """
    html = render_to_string(f"correos/{plantilla}.html", {**contexto, "asunto": asunto})
    mensaje = EmailMultiAlternatives(asunto, texto, None, [destinatario])
    mensaje.attach_alternative(html, "text/html")
    mensaje.mixed_subtype = "related"
    logo = MIMEImage(_bytes_del_logo(), _subtype="png")
    logo.add_header("Content-ID", f"<{LOGO_CID}>")
    logo.add_header("Content-Disposition", "inline", filename=LOGO.name)
    mensaje.attach(logo)
    return mensaje


def enviar(mensajes):
    """Entrega los correos por una sola conexión, sin hacer esperar a quien hizo la petición.

    Con SMTP real, varios destinatarios tardan más de lo que el frontend espera a la API
    (`ADMIND_API_TIEMPO_ESPERA`). Por eso, con `CORREO_EN_SEGUNDO_PLANO`, el envío sale en un
    hilo aparte. Un fallo se registra y no se propaga: el aviso ya quedó en la bandeja.
    """
    if not mensajes:
        return
    if settings.CORREO_EN_SEGUNDO_PLANO:
        threading.Thread(target=_entregar, args=(mensajes,), daemon=True).start()
    else:
        _entregar(mensajes)


def _entregar(mensajes):
    try:
        get_connection().send_messages(mensajes)
    except Exception:
        logger.exception("No se pudieron enviar %s correos: %s", len(mensajes), mensajes[0].subject)
