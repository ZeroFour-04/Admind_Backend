"""Unidades del conjunto activo y enrutamiento por vínculos (maestro §5.5). No saben nada de HTTP.

El enrutamiento decide **a quién** le llega un hecho sobre una unidad. **Por dónde** le llega
lo decide el canal de `apps/notificaciones/`.
"""
from enum import Enum

from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.auditoria import servicios as auditoria
from apps.comun.aislamiento.contexto import conjunto_activo_id
from apps.permisos.models import Asignacion
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


class NombreRepetido(Exception):
    """Ya hay una unidad con ese nombre en el conjunto."""


class PersonaSinAsignacion(Exception):
    """La persona no tiene un rol vigente en el conjunto activo (plan P3). Primero se vincula (HU-07)."""


class VinculoDuplicado(Exception):
    """La persona ya tiene un vínculo vigente de ese tipo sobre la unidad."""


class VinculoYaCerrado(Exception):
    """El vínculo ya tenía fecha de cierre."""


class CierreAntesDelInicio(Exception):
    """La fecha de cierre es anterior al inicio del vínculo."""


def unidades_del_conjunto():
    """Las unidades con cuántos vínculos vigentes tiene cada una."""
    hoy = timezone.localdate()
    vigente = Q(vinculos__vigencia_desde__lte=hoy) & (
        Q(vinculos__vigencia_hasta__isnull=True) | Q(vinculos__vigencia_hasta__gt=hoy)
    )
    return Unidad.objects.annotate(vinculos_vigentes=Count("vinculos", filter=vigente)).order_by("nombre")


def destinatarios(unidad, hecho):
    """Las personas que deben enterarse de ese hecho sobre esa unidad."""
    vinculos = VinculoUnidad.objects.vigentes().filter(unidad=unidad).filter(VINCULOS_POR_HECHO[hecho])
    return Persona.objects.filter(pk__in=vinculos.values("persona_id"))


def unidades_de(persona):
    """Las unidades del conjunto activo sobre las que la persona tiene un vínculo vigente."""
    return Unidad.objects.filter(pk__in=VinculoUnidad.objects.vigentes().filter(persona=persona).values("unidad_id"))


def unidades_para_solicitar(persona):
    """Las unidades a cuyo nombre la persona puede solicitar: vínculo vigente y `reside` (maestro §5.10)."""
    vinculos = VinculoUnidad.objects.vigentes().filter(persona=persona, reside=True)
    return Unidad.objects.filter(pk__in=vinculos.values("unidad_id")).order_by("nombre")


def crear_unidad(actor, nombre):
    try:
        with transaction.atomic():
            unidad = Unidad.objects.create(nombre=nombre)
            auditoria.registrar(actor, "unidad.crear", "Unidad", unidad.id, despues={"nombre": nombre})
    except IntegrityError as error:
        if "unidad_nombre_unico_en_conjunto" in str(error):
            raise NombreRepetido() from error
        raise
    return unidad


def detalle_de_unidad(unidad):
    """Vínculos vigentes y el histórico: los cerrados y los que todavía no empiezan."""
    vinculos = VinculoUnidad.objects.filter(unidad=unidad).select_related("persona").order_by("-vigencia_desde")
    vigentes = list(vinculos.vigentes())
    ids_vigentes = {vinculo.id for vinculo in vigentes}
    return {"vigentes": vigentes, "historicos": [v for v in vinculos if v.id not in ids_vigentes]}


def datos_del_vinculo(vinculo):
    return {
        "persona": vinculo.persona_id,
        "unidad": vinculo.unidad_id,
        "tipo": vinculo.tipo,
        "reside": vinculo.reside,
        "vigencia_desde": vinculo.vigencia_desde,
        "vigencia_hasta": vinculo.vigencia_hasta,
    }


def registrar_vinculo(actor, unidad, persona_id, tipo, reside, vigencia_desde=None):
    """Solo para quien ya tiene un rol vigente en el conjunto: así no se sondean personas ajenas (P3)."""
    en_el_conjunto = Asignacion.objects.vigentes().filter(persona_id=persona_id, conjunto_id=conjunto_activo_id())
    if not en_el_conjunto.exists():
        raise PersonaSinAsignacion()
    abiertos = VinculoUnidad.objects.filter(unidad=unidad, persona_id=persona_id, tipo=tipo)
    if abiertos.filter(vigencia_hasta__isnull=True).exists() or abiertos.vigentes().exists():
        raise VinculoDuplicado()
    try:
        with transaction.atomic():
            vinculo = VinculoUnidad.objects.create(
                unidad=unidad,
                persona_id=persona_id,
                tipo=tipo,
                reside=reside,
                vigencia_desde=vigencia_desde or timezone.localdate(),
            )
            auditoria.registrar(actor, "vinculo.registrar", "VinculoUnidad", vinculo.id, despues=datos_del_vinculo(vinculo))
    except IntegrityError as error:
        # Dos registros iguales a la vez: la base decide.
        if "vinculo_vigente_unico" in str(error):
            raise VinculoDuplicado() from error
        raise
    return vinculo


def cerrar_vinculo(actor, vinculo, vigencia_hasta=None):
    """`vigencia_hasta` es el primer día sin el vínculo; por defecto, hoy (plan P5). La fila se conserva."""
    vigencia_hasta = vigencia_hasta or timezone.localdate()
    if vinculo.vigencia_hasta is not None:
        raise VinculoYaCerrado()
    if vigencia_hasta < vinculo.vigencia_desde:
        raise CierreAntesDelInicio()
    antes = datos_del_vinculo(vinculo)
    with transaction.atomic():
        vinculo.vigencia_hasta = vigencia_hasta
        vinculo.save(update_fields=["vigencia_hasta"])
        auditoria.registrar(
            actor, "vinculo.cerrar", "VinculoUnidad", vinculo.id, antes=antes, despues=datos_del_vinculo(vinculo)
        )
    return vinculo
