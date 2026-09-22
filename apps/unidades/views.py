from rest_framework.response import Response

from apps.comun.aislamiento.vistas import VistaDeConjunto
from apps.permisos.views import exigir_permiso
from apps.unidades import servicios
from apps.unidades.serializers import UnidadSerializer


class UnidadesView(VistaDeConjunto):
    """Las unidades del conjunto activo.

    Por ahora solo la usa el anuncio dirigido a una vivienda (HU-25). La gestión de unidades y
    vínculos, con su pantalla, es de HU-08.
    """

    def get(self, request):
        exigir_permiso(request, "vinculo.gestionar", "anuncio.dirigir")
        return Response(UnidadSerializer(servicios.unidades_del_conjunto(), many=True).data)
