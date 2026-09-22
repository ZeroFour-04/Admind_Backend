from rest_framework.permissions import BasePermission

from apps.cuentas import dos_factores


class DosFactoresAlDia(BasePermission):
    """Con algún permiso sensible, nada funciona hasta verificar el segundo factor (HU-02, maestro §7.2).

    Va en los permisos por defecto de DRF, junto a IsAuthenticated. Las vistas que se necesitan
    para llegar a verificarlo lo declaran con `permitida_sin_segundo_factor = True`.
    """

    message = "Debes verificar el segundo factor antes de continuar."

    def has_permission(self, request, view):
        if getattr(view, "permitida_sin_segundo_factor", False):
            return True
        sesion = request.auth
        if sesion is None:
            return True  # sin token responde IsAuthenticated, con 401
        return not dos_factores.pendiente(sesion)
