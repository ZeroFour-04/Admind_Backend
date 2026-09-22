"""Qué puede hacer una persona y dónde. Los permisos se calculan, no se guardan."""
from django.db.models import Q

from apps.conjuntos.models import Conjunto
from apps.permisos.catalogo import PERMISOS_POR_ROL, PERMISOS_SENSIBLES, Rol
from apps.permisos.models import Asignacion


def es_superusuario(persona):
    return Asignacion.objects.vigentes().filter(persona=persona, rol=Rol.SUPERUSUARIO).exists()


def conjuntos_disponibles(persona):
    """Conjuntos activos donde la persona puede operar (HU-26).

    El Superusuario gobierna la plataforma: puede elegir cualquiera. El resto, solo aquellos
    donde tiene al menos una asignación vigente; nadie ve los conjuntos de otros.
    """
    conjuntos = Conjunto.objects.filter(activo=True).order_by("nombre")
    if es_superusuario(persona):
        return conjuntos
    con_asignacion = Asignacion.objects.vigentes().filter(persona=persona).values("conjunto_id")
    return conjuntos.filter(pk__in=con_asignacion)


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


def tiene_permiso(persona, conjunto_id, permiso):
    return permiso in permisos_efectivos(persona, conjunto_id)


def tiene_permisos_sensibles(persona):
    """Si alguno de sus roles vigentes, en cualquier conjunto, trae un permiso sensible (HU-02).

    Se mira en todos los conjuntos y no solo en el activo: el segundo factor se pide al entrar,
    antes de elegir conjunto.
    """
    roles = Asignacion.objects.vigentes().filter(persona=persona).values_list("rol", flat=True).distinct()
    return any(PERMISOS_POR_ROL[rol] & PERMISOS_SENSIBLES for rol in roles)
