"""Buscar a una persona por documento exacto y vincularla al conjunto activo (HU-07, R12). No sabe nada de HTTP.

Es el punto blando del diseño: la tabla de personas es global. Por eso la búsqueda es exacta,
queda en la auditoría y tiene un límite por administrador (plan D6).
"""
from datetime import timedelta

from django.utils import timezone

from apps.auditoria import servicios as auditoria
from apps.permisos.models import Asignacion
from apps.permisos.servicios import asignar_rol
from apps.personas.models import Persona, normalizar_documento

LIMITE_DE_BUSQUEDAS = 20
VENTANA_DE_BUSQUEDAS = timedelta(hours=1)


class LimiteDeBusquedas(Exception):
    """El administrador ya hizo el máximo de búsquedas permitidas en la última hora."""


class PersonaNoEncontrada(Exception):
    """No existe una persona con ese identificador."""


def buscar(actor, tipo_documento, numero_documento):
    """La persona con ese tipo y número exactos, o None. Cada búsqueda queda en la auditoría, encuentre o no."""
    if auditoria.contar(actor, "persona.buscar", timezone.now() - VENTANA_DE_BUSQUEDAS) >= LIMITE_DE_BUSQUEDAS:
        raise LimiteDeBusquedas()
    numero = normalizar_documento(numero_documento)
    persona = Persona.objects.filter(tipo_documento=tipo_documento, numero_documento=numero).first()
    auditoria.registrar(
        actor,
        "persona.buscar",
        "Persona",
        persona.id if persona else None,
        detalle={"tipo_documento": tipo_documento, "numero_documento": numero},
    )
    return persona


def resumen(persona, conjunto_id):
    """Lo mínimo para decidir si vincularla: sin teléfono, sin correo, sin datos de otros conjuntos."""
    asignaciones = Asignacion.objects.vigentes().filter(persona=persona, conjunto_id=conjunto_id)
    return {
        "id": persona.id,
        "nombre": str(persona),
        # Toda alta crea la cuenta; una persona sin cuenta llegará con la importación (HU-36, plan D10).
        "tiene_cuenta": hasattr(persona, "usuario"),
        "roles_en_el_conjunto": [asignacion.get_rol_display() for asignacion in asignaciones],
    }


def vincular(actor, persona_id, rol, conjunto_id):
    """Le da un rol en el conjunto activo sin crear otra persona (HU-04). Reutiliza la asignación de HU-06."""
    persona = Persona.objects.filter(pk=persona_id).first()
    if persona is None:
        raise PersonaNoEncontrada()
    asignar_rol(actor, persona, rol, conjunto_id)
    return persona
