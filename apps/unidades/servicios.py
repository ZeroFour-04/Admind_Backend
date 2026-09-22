"""Unidades del conjunto activo y enrutamiento por vínculos (maestro §5.5). No saben nada de HTTP.

El enrutamiento decide **a quién** le llega un hecho sobre una unidad. **Por dónde** le llega
lo decide el canal de `apps/notificaciones/`.
"""
from enum import Enum

from django.db.models import Q

from apps.personas.models import Persona
from apps.unidades.models import TipoVinculo, Unidad, VinculoUnidad


class Hecho(Enum):
    ANUNCIO_A_VIVIENDA = "anuncio_a_vivienda"
    OPERATIVO = "operativo"
    ASAMBLEA = "asamblea"
    INFRACCION = "infraccion"
    MORA = "mora"


# Qué vínculos vigentes de la unidad reciben cada hecho. Es una consulta, no un IF sobre roles.
VINCULOS_POR_HECHO = {
    # Propietario y arrendatario, residan o no (maestro §5.7, HU-25).
    Hecho.ANUNCIO_A_VIVIENDA: Q(),
    # Reserva, anuncio operativo, visitante en portería: quien vive ahí.
    Hecho.OPERATIVO: Q(reside=True),
    # Convocatoria y acta de asamblea: el propietario, aunque no resida (art. 39).
    Hecho.ASAMBLEA: Q(tipo=TipoVinculo.PROPIETARIO),
    # Comunicación de infracción: propietario y arrendatario, ambos (C-318/02).
    Hecho.INFRACCION: Q(),
    # Mora y paz y salvo: el propietario, que es el obligado.
    Hecho.MORA: Q(tipo=TipoVinculo.PROPIETARIO),
}


def unidades_del_conjunto():
    return Unidad.objects.order_by("nombre")


def destinatarios(unidad, hecho):
    """Las personas que deben enterarse de ese hecho sobre esa unidad."""
    vinculos = VinculoUnidad.objects.vigentes().filter(unidad=unidad).filter(VINCULOS_POR_HECHO[hecho])
    return Persona.objects.filter(pk__in=vinculos.values("persona_id"))


def unidades_de(persona):
    """Las unidades del conjunto activo sobre las que la persona tiene un vínculo vigente."""
    return Unidad.objects.filter(pk__in=VinculoUnidad.objects.vigentes().filter(persona=persona).values("unidad_id"))
