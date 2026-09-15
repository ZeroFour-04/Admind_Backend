"""Qué puede hacer una persona y dónde. Los permisos se calculan, no se guardan."""
from django.db.models import Q

from apps.conjuntos.models import Conjunto
from apps.permisos.catalogo import PERMISOS_POR_ROL
from apps.permisos.models import Asignacion


def conjuntos_disponibles(persona):
    """Conjuntos activos donde la persona tiene al menos una asignación vigente (HU-26)."""
    con_asignacion = Asignacion.objects.vigentes().filter(persona=persona).values("conjunto_id")
    return Conjunto.objects.filter(activo=True, pk__in=con_asignacion).order_by("nombre")


def puede_operar_en(persona, conjunto_id):
    return conjuntos_disponibles(persona).filter(pk=conjunto_id).exists()


def permisos_efectivos(persona, conjunto_id):
    """Unión de los permisos de sus roles vigentes en ese conjunto y de sus roles de plataforma.

    Un rol de otro conjunto no aporta nada (HU-06). Sin conjunto, solo cuentan los de plataforma.
    """
    roles = (
        Asignacion.objects.vigentes()
        .filter(persona=persona)
        .filter(Q(conjunto_id=conjunto_id) | Q(conjunto__isnull=True))
        .values_list("rol", flat=True)
    )
    permisos = set()
    for rol in roles:
        permisos |= PERMISOS_POR_ROL[rol]
    return permisos
