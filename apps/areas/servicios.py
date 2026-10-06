"""Catálogo de áreas comunes del conjunto activo (HU-09). No sabe nada de HTTP.

Toda escritura deja registro en la auditoría con los campos que cambiaron.
"""
from datetime import datetime, timedelta

from django.db import IntegrityError, transaction

from apps.areas.models import Area
from apps.auditoria import servicios as auditoria
from apps.permisos.servicios import tiene_permiso

CAMPOS_EDITABLES = ("nombre", "descripcion", "hora_apertura", "hora_cierre", "duracion_franja_minutos", "aforo_maximo")


class NombreRepetido(Exception):
    """Ya hay un área con ese nombre en el conjunto."""


class AreaYaInactiva(Exception):
    """El área ya estaba desactivada."""


def areas_visibles(persona, conjunto_id):
    """Con `area.gestionar`, todas; si no, solo las activas."""
    areas = Area.objects.order_by("nombre")
    if tiene_permiso(persona, conjunto_id, "area.gestionar"):
        return areas
    return areas.filter(activo=True)


def crear(actor, **datos):
    try:
        with transaction.atomic():
            area = Area.objects.create(**datos)
            auditoria.registrar(actor, "area.crear", "Area", area.id, despues=datos)
    except IntegrityError as error:
        if "area_nombre_unico_en_conjunto" in str(error):
            raise NombreRepetido() from error
        raise
    return area


def cambiar(actor, area, accion, **campos):
    """Guarda los campos que cambiaron y deja `antes` y `despues` en la auditoría."""
    cambiados = {campo: valor for campo, valor in campos.items() if getattr(area, campo) != valor}
    if not cambiados:
        return area
    antes = {campo: getattr(area, campo) for campo in cambiados}
    try:
        with transaction.atomic():
            for campo, valor in cambiados.items():
                setattr(area, campo, valor)
            area.save(update_fields=list(cambiados))
            auditoria.registrar(actor, accion, "Area", area.id, antes=antes, despues=cambiados)
    except IntegrityError as error:
        for campo, valor in antes.items():
            setattr(area, campo, valor)
        if "area_nombre_unico_en_conjunto" in str(error):
            raise NombreRepetido() from error
        raise
    return area


def editar(actor, area, **datos):
    return cambiar(actor, area, "area.editar", **{campo: datos[campo] for campo in CAMPOS_EDITABLES if campo in datos})


def poner_en_mantenimiento(actor, area, en_mantenimiento):
    """Un área en mantenimiento sigue en el catálogo pero no admite solicitudes (HU-09)."""
    return cambiar(actor, area, "area.mantenimiento", en_mantenimiento=en_mantenimiento)


def desactivar(actor, area):
    """Deja `activo = False`. Nunca borra (maestro §5.11)."""
    if not area.activo:
        raise AreaYaInactiva()
    return cambiar(actor, area, "area.desactivar", activo=False)


def franjas_del_dia(area, fecha):
    """Los bloques `(hora_inicio, hora_fin)` del día, desde la apertura y sin pasar el cierre (plan D1 a)."""
    duracion = timedelta(minutes=area.duracion_franja_minutos)
    inicio = datetime.combine(fecha, area.hora_apertura)
    cierre = datetime.combine(fecha, area.hora_cierre)
    franjas = []
    while inicio + duracion <= cierre:
        franjas.append((inicio.time(), (inicio + duracion).time()))
        inicio += duracion
    return franjas
