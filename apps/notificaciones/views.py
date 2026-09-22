from rest_framework.response import Response

from apps.comun.aislamiento.vistas import VistaDeConjunto
from apps.notificaciones import servicios
from apps.notificaciones.serializers import NotificacionSerializer


class BandejaView(VistaDeConjunto):
    """Los avisos de quien pregunta, en el conjunto activo. Cada persona ve solo los suyos."""

    def get(self, request):
        return Response(NotificacionSerializer(servicios.bandeja(request.user.persona), many=True).data)
