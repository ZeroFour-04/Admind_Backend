"""Reglas beta de reserva del conjunto activo (HU-10). No saben nada de HTTP.

Editar es versionar: la regla vieja se cierra y la nueva la reemplaza (plan D4). Todo queda en la auditoría.
"""
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.areas.models import Area
from apps.auditoria import servicios as auditoria
from apps.reglas import catalogo
from apps.reglas.models import Regla


class AreaNoEncontrada(Exception):
    """El área no existe en el conjunto activo o está inactiva."""


class ReglaCerrada(Exception):
    """La regla ya no está vigente: no se edita ni se retira otra vez."""


def datos_de_la_regla(regla):
    return {
        "area": regla.area_id,
        "tipo": regla.tipo,
        "parametros": regla.parametros,
        "vigencia_desde": regla.vigencia_desde,
        "vigencia_hasta": regla.vigencia_hasta,
        "reemplaza": regla.reemplaza_id,
    }


def reglas_actuales():
    """Las vigentes hoy y las que empiezan después. Las cerradas quedan en el historial."""
    hoy = timezone.localdate()
    return (
        Regla.objects.filter(Q(vigencia_hasta__isnull=True) | Q(vigencia_hasta__gt=hoy))
        .select_related("area", "creada_por")
        .order_by("area__nombre", "tipo", "vigencia_desde")
    )


def reglas_vigentes(area, fecha):
    """Las reglas del área que aplican ese día. Las consume el evaluador (HU-13)."""
    return Regla.objects.vigentes(fecha).filter(area=area).order_by("tipo", "creada_en")


def crear(actor, area_id, tipo, parametros, vigencia_desde):
    area = Area.objects.filter(pk=area_id, activo=True).first()
    if area is None:
        raise AreaNoEncontrada()
    normalizados = catalogo.validar(tipo, parametros, area)
    with transaction.atomic():
        regla = Regla.objects.create(
            area=area, tipo=tipo, parametros=normalizados, vigencia_desde=vigencia_desde, creada_por=actor
        )
        auditoria.registrar(actor, "regla.crear", "Regla", regla.id, despues=datos_de_la_regla(regla))
    return regla


def cerrar(regla, desde):
    """Cierra la vigencia en `desde`, o al empezar si la regla todavía no había empezado."""
    regla.vigencia_hasta = max(desde, regla.vigencia_desde)
    regla.save(update_fields=["vigencia_hasta"])


def editar(actor, regla, parametros):
    """Cierra la regla y crea la versión nueva que la reemplaza, con autor y fecha (HU-10)."""
    if regla.vigencia_hasta is not None:
        raise ReglaCerrada()
    normalizados = catalogo.validar(regla.tipo, parametros, regla.area)
    antes = datos_de_la_regla(regla)
    inicio = max(timezone.localdate(), regla.vigencia_desde)
    with transaction.atomic():
        cerrar(regla, inicio)
        nueva = Regla.objects.create(
            area=regla.area,
            tipo=regla.tipo,
            parametros=normalizados,
            vigencia_desde=inicio,
            reemplaza=regla,
            creada_por=actor,
        )
        auditoria.registrar(actor, "regla.editar", "Regla", nueva.id, antes=antes, despues=datos_de_la_regla(nueva))
    return nueva


def retirar(actor, regla):
    """Cierra la vigencia hoy. La regla se conserva en el historial."""
    if regla.vigencia_hasta is not None:
        raise ReglaCerrada()
    antes = datos_de_la_regla(regla)
    with transaction.atomic():
        cerrar(regla, timezone.localdate())
        auditoria.registrar(actor, "regla.retirar", "Regla", regla.id, antes=antes, despues=datos_de_la_regla(regla))
    return regla
