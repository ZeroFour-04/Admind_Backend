"""Ayudante de las vistas para exigir un permiso del catálogo (HU-06)."""
from rest_framework.exceptions import PermissionDenied

from apps.permisos.servicios import tiene_permiso

MENSAJE_SIN_PERMISO = "No tienes permiso para hacer esto."


def exigir_permiso(request, *permisos):
    """Corta la petición con 403 si la persona no tiene ninguno de los permisos en su conjunto activo."""
    conjunto_id = getattr(request.auth, "conjunto_activo_id", None)
    if not any(tiene_permiso(request.user.persona, conjunto_id, permiso) for permiso in permisos):
        raise PermissionDenied(MENSAJE_SIN_PERMISO)
