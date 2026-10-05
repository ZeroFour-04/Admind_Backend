"""Límites de intentos de las vistas públicas de cuentas. Se declaran en la vista, como los permisos."""
from rest_framework.throttling import SimpleRateThrottle

from apps.cuentas.servicios import huella_de


class LimiteDeEnlacesPorCorreo(SimpleRateThrottle):
    """A lo sumo 3 enlaces de recuperación por hora para un mismo correo, exista o no la cuenta (HU-01).

    DRF guarda en la caché la hora de cada petición. La caché es la memoria del proceso: la
    cuenta se pierde al reiniciar el servidor y no se comparte entre procesos.
    """

    scope = "recuperar_contrasena"
    rate = "3/hour"

    def get_cache_key(self, request, view):
        correo = request.data.get("correo") if isinstance(request.data, dict) else None
        if not isinstance(correo, str) or not correo.strip():
            # Sin correo no hay a quién contarle: el serializer responde 400.
            return None
        # La huella y no el correo: la clave queda de largo fijo y el correo no se guarda en claro.
        return self.cache_format % {"scope": self.scope, "ident": huella_de(correo.strip().lower())}