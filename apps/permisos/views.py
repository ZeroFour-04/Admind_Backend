"""Ayudante de las vistas para exigir un permiso del catálogo (HU-06)."""
from rest_framework.exceptions import PermissionDenied

from apps.permisos.servicios import tiene_permiso

MENSAJE_SIN_PERMISO = "No tienes permiso para hacer esto."


def tiene_permiso_en_conjunto(request, permiso):
    """Si la persona tiene ese permiso en su conjunto activo. Para decidir qué datos van en la respuesta."""
    conjunto_id = getattr(request.auth, "conjunto_activo_id", None)
    return tiene_permiso(request.user.persona, conjunto_id, permiso)


def exigir_permiso(request, *permisos):
    """Corta la petición con 403 si la persona no tiene ninguno de los permisos en su conjunto activo."""
    conjunto_id = getattr(request.auth, "conjunto_activo_id", None)
    if not any(tiene_permiso(request.user.persona, conjunto_id, permiso) for permiso in permisos):
        raise PermissionDenied(MENSAJE_SIN_PERMISO)
