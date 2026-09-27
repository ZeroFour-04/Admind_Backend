"""Registro de auditoría de solo inserción (maestro §5.11). No sabe nada de HTTP.

No importa ninguna app de negocio: todas la usan a ella (apps/README.md).
"""
from apps.auditoria.models import Registro


def registrar(actor, accion, entidad, entidad_id=None, *, antes=None, despues=None, detalle=None,
              via_superusuario=False):
    """Deja una fila en el conjunto activo. `via_superusuario` lo decide quien llama (plan P15)."""
    return Registro.objects.create(
        actor=actor,
        accion=accion,
        entidad=entidad,
        entidad_id=entidad_id,
        antes=antes,
        despues=despues,
        detalle=detalle,
        via_superusuario=via_superusuario,
    )


def contar(actor, accion, desde):
    """Cuántas veces hizo esa acción en el conjunto activo desde ese momento. La usa el límite de HU-07."""
    return Registro.objects.filter(actor=actor, accion=accion, creado_en__gte=desde).count()
