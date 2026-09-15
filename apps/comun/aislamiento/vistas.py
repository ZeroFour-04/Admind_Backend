from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.views import APIView

from apps.comun.aislamiento.contexto import contexto_limpio, fijar_conjunto_activo

CLAVES_PROHIBIDAS = {"conjunto", "conjunto_id"}


class VistaDeConjunto(APIView):
    """Base de toda vista con datos de un conjunto (maestro §5.4, HU-05).

    Hace lo que el maestro llama middleware. No puede ser un middleware de Django porque DRF
    autentica el token dentro de la vista, después de que los middleware ya corrieron.
    """

    def dispatch(self, request, *args, **kwargs):
        with contexto_limpio():
            return super().dispatch(request, *args, **kwargs)

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)  # autentica el token y revisa permisos

        claves_del_cuerpo = set(request.data.keys()) if hasattr(request.data, "keys") else set()
        if CLAVES_PROHIBIDAS & (set(kwargs) | set(request.query_params) | claves_del_cuerpo):
            raise ValidationError("El conjunto no se envía en la petición: sale de la sesión.")

        conjunto_id = getattr(request.auth, "conjunto_activo_id", None)
        if conjunto_id is None:
            raise PermissionDenied("Debe elegir un conjunto activo.")
        fijar_conjunto_activo(conjunto_id)
