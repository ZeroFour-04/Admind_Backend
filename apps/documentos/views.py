"""El reglamento del conjunto activo (HU-33, lo mínimo). Cada vista valida, exige su permiso y llama al servicio."""
from django.http import HttpResponse
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from apps.comun.aislamiento.vistas import VistaDeConjunto
from apps.documentos import servicios
from apps.documentos.serializers import ReglamentoSerializer, SubirReglamentoSerializer
from apps.permisos.views import exigir_permiso


def datos_del_reglamento(reglamento):
    if reglamento is None:
        return {"cargado": False}
    return {"cargado": True, **ReglamentoSerializer(reglamento).data}


class ReglamentoView(VistaDeConjunto):
    """Los datos del reglamento vigente, y subir uno nuevo. No recibe el conjunto: es el activo."""

    def get(self, request):
        exigir_permiso(request, "documento.ver", "documento.subir")
        return Response(datos_del_reglamento(servicios.vigente()))

    def put(self, request):
        exigir_permiso(request, "documento.subir")
        datos = SubirReglamentoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        archivo = datos.validated_data["archivo"]
        # Se lee un byte más del límite: basta para saber que se pasa, sin cargar un archivo enorme.
        contenido = archivo.read(servicios.TAMANO_MAXIMO + 1)
        try:
            reglamento = servicios.guardar(request.user.persona, archivo.name, contenido)
        except servicios.ReglamentoInvalido as error:
            return Response({"archivo": [error.mensaje]}, status=status.HTTP_400_BAD_REQUEST)
        return Response(datos_del_reglamento(reglamento))


class ArchivoDelReglamentoView(VistaDeConjunto):
    """El PDF del reglamento vigente."""

    def get(self, request):
        exigir_permiso(request, "documento.descargar", "documento.subir")
        reglamento = servicios.vigente(con_contenido=True)
        if reglamento is None:
            raise NotFound()
        respuesta = HttpResponse(bytes(reglamento.contenido), content_type="application/pdf")
        respuesta["Content-Disposition"] = 'inline; filename="reglamento.pdf"'
        return respuesta
