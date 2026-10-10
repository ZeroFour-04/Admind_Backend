"""Reglas de reserva del conjunto activo: del conjunto (alfa) y de cada área (beta) (HU-10). No saben nada de HTTP.

Editar es versionar: la regla vieja se cierra y la nueva la reemplaza (plan D4). Todo queda en la auditoría.
"""
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.areas.models import Area
from apps.auditoria import servicios as auditoria
from apps.reglas import catalogo
from apps.reglas.models import Regla
from apps.reservas.models import EstadoSolicitud, Solicitud


class AreaNoEncontrada(Exception):
    """El área no existe en el conjunto activo o está inactiva."""


class ReglaCerrada(Exception):
    """La regla ya no está vigente: no se edita ni se retira otra vez."""


class NivelEquivocado(Exception):
    """Una regla del conjunto con área, o una de un área sin ella. Trae el mensaje para el campo."""

    def __init__(self, mensaje):
        super().__init__(mensaje)
        self.mensaje = mensaje


class ReglaYaDefinida(Exception):
    """Ya hay una regla abierta de ese tipo: se cambia o se retira, no se repite (P5)."""


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
    """Las abiertas: primero las del conjunto y después las de cada área. Las cerradas quedan en el historial."""
    return (
        Regla.objects.abiertas()
        .select_related("area", "creada_por")
        .order_by(F("area__nombre").asc(nulls_first=True), "tipo", "vigencia_desde")
    )


def reglas_vigentes(area, fecha):
    """Las del conjunto y las del área que aplican ese día, en ese orden. Las consume el evaluador (HU-13)."""
    return (
        Regla.objects.vigentes(fecha)
        .filter(Q(area__isnull=True) | Q(area=area), tipo__in=list(catalogo.NIVEL_POR_TIPO))
        .order_by(F("area").asc(nulls_first=True), "tipo", "creada_en")
    )


def reservas_en_cierre(area, renglones):
    """Cuántas solicitudes apartadas o reservadas, de hoy en adelante, caen en días que el área no abre."""
    fechas = Solicitud.objects.filter(
        area=area,
        estado__in=[EstadoSolicitud.APARTADA, EstadoSolicitud.RESERVADA],
        fecha__gte=timezone.localdate(),
    ).values_list("fecha", flat=True)
    return sum(1 for fecha in fechas if catalogo.motivos_del_dia(fecha, renglones))


def crear(actor, tipo, parametros, vigencia_desde, area_id=None):
    """Define una regla. El nivel lo dice el catálogo: del conjunto, sin área; de un área, con ella."""
    normalizados = catalogo.validar(tipo, parametros)
    area = None
    if catalogo.NIVEL_POR_TIPO[tipo] == catalogo.Nivel.ALFA:
        if area_id is not None:
            raise NivelEquivocado("Esta regla es del conjunto: no lleva área.")
    else:
        if area_id is None:
            raise NivelEquivocado("Esta regla es de un área: elige cuál.")
        area = Area.objects.filter(pk=area_id, activo=True).first()
        if area is None:
            raise AreaNoEncontrada()
        if area.modo_uso not in catalogo.MODOS_POR_TIPO[tipo]:
            raise NivelEquivocado(
                "Esta regla no aplica a un área con ingreso."
                if area.modo_uso == catalogo.MODO_INGRESO
                else "Esta regla no aplica a un área con reserva."
            )
    if Regla.objects.abiertas().filter(tipo=tipo, area=area).exists():
        raise ReglaYaDefinida()
    try:
        with transaction.atomic():
            regla = Regla.objects.create(
                area=area, tipo=tipo, parametros=normalizados, vigencia_desde=vigencia_desde, creada_por=actor
            )
            auditoria.registrar(actor, "regla.crear", "Regla", regla.id, despues=datos_de_la_regla(regla))
    except IntegrityError as error:
        # Dos personas definiendo la misma regla a la vez: decide la restricción única de la base.
        if "unica_abierta" in str(error):
            raise ReglaYaDefinida() from error
        raise
    return regla


def cerrar(regla, desde):
    """Cierra la vigencia en `desde`, o al empezar si la regla todavía no había empezado."""
    regla.vigencia_hasta = max(desde, regla.vigencia_desde)
    regla.save(update_fields=["vigencia_hasta"])


def editar(actor, regla, parametros):
    """Cierra la regla y crea la versión nueva que la reemplaza, con autor y fecha (HU-10)."""
    if regla.vigencia_hasta is not None:
        raise ReglaCerrada()
    normalizados = catalogo.validar(regla.tipo, parametros)
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
