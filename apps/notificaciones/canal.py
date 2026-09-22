"""Canal de notificaciones (maestro §3.1): un componente, dos salidas, la aplicación y el correo.

Decide **por dónde** llega un aviso. **A quién** lo decide quien lo llama: con el enrutamiento
por vínculos de `apps/unidades/` o con las asignaciones del conjunto.
"""
import logging
import uuid
from dataclasses import dataclass

from django.core.mail import send_mass_mail
from django.db import transaction

from apps.comun.aislamiento.contexto import conjunto_activo_id
from apps.conjuntos.models import Conjunto
from apps.cuentas.models import Usuario
from apps.notificaciones.models import Notificacion

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Aviso:
    titulo: str
    cuerpo: str
    origen: str  # el módulo que avisa, p. ej. "anuncio"
    referencia: uuid.UUID  # el registro que lo originó


def notificar(aviso, persona_ids):
    """Deja el aviso en la bandeja de cada persona y, cuando se confirma la transacción, se lo manda por correo.

    A quien ya lo recibió no se le repite: el mismo hecho avisa una sola vez. Devuelve los ids de
    las personas avisadas ahora.
    """
    nuevas = en_la_aplicacion(aviso, persona_ids)
    if nuevas:
        conjunto_id = conjunto_activo_id()
        transaction.on_commit(lambda: por_correo(aviso, nuevas, conjunto_id))
    return nuevas


def en_la_aplicacion(aviso, persona_ids):
    ya_avisadas = set(
        Notificacion.objects.filter(origen=aviso.origen, referencia=aviso.referencia).values_list("persona_id", flat=True)
    )
    nuevas = sorted(set(persona_ids) - ya_avisadas)
    # bulk_create se salta save(), así que el conjunto se fija aquí: siempre el activo.
    conjunto_id = conjunto_activo_id()
    Notificacion.objects.bulk_create(
        Notificacion(
            conjunto_id=conjunto_id,
            persona_id=persona_id,
            titulo=aviso.titulo,
            cuerpo=aviso.cuerpo,
            origen=aviso.origen,
            referencia=aviso.referencia,
        )
        for persona_id in nuevas
    )
    return nuevas


def por_correo(aviso, persona_ids, conjunto_id):
    """Un correo por persona, así nadie ve a quién más le llegó. Solo a cuentas que pueden entrar.

    Un fallo del servidor de correo no deshace el aviso: ya quedó en la bandeja.
    """
    correos = Usuario.objects.filter(
        persona_id__in=persona_ids, is_active=True, persona__activo=True
    ).values_list("correo", flat=True)
    conjunto = Conjunto.objects.get(pk=conjunto_id)
    asunto = f"AdMind · {conjunto.nombre}: {aviso.titulo}"
    try:
        send_mass_mail([(asunto, aviso.cuerpo, None, [correo]) for correo in correos])
    except Exception:
        logger.exception("No se pudo enviar por correo el aviso %s %s", aviso.origen, aviso.referencia)
