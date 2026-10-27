"""Los documentos del conjunto activo (HU-33). Cada vista valida, exige su permiso y llama al servicio.

El residente descarga lo vigente con `documento.ver`; las versiones archivadas piden `documento.descargar`
(sensible, con segundo factor). Toda descarga queda en la auditoría.
"""
from django.http import HttpResponse
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from apps.comun.aislamiento.vistas import VistaDeConjunto
from apps.documentos import servicios
from apps.documentos.serializers import SubirDocumentoSerializer, VersionSerializer, datos_del_documento
from apps.permisos.views import exigir_permiso


def pdf(documento, tipo):
    respuesta = HttpResponse(bytes(documento.contenido), content_type="application/pdf")
    respuesta["Content-Disposition"] = f'inline; filename="{tipo}.pdf"'
    return respuesta


class DocumentosView(VistaDeConjunto):
    """El vigente de cada tipo, sin el contenido: lo que muestra la pantalla «Documentos»."""

    def get(self, request):
        exigir_permiso(request, "documento.ver", "documento.subir")
        return Response([datos_del_documento(tipo, documento) for tipo, documento in servicios.vigentes()])


class DocumentoView(VistaDeConjunto):
    """Los datos del documento vigente de un tipo, y subir una versión nueva. No recibe el conjunto: es el activo."""

    def get(self, request, tipo):
        exigir_permiso(request, "documento.ver", "documento.subir")
        return Response(datos_del_documento(tipo, servicios.vigente(tipo)))

    def put(self, request, tipo):
        exigir_permiso(request, "documento.subir")
        datos = SubirDocumentoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        archivo = datos.validated_data["archivo"]
        # Se lee un byte más del límite: basta para saber que se pasa, sin cargar un archivo enorme.
        contenido = archivo.read(servicios.TAMANO_MAXIMO + 1)
        try:
            documento = servicios.guardar(request.user.persona, tipo, archivo.name, contenido)
        except servicios.DocumentoInvalido as error:
            return Response({"archivo": [error.mensaje]}, status=status.HTTP_400_BAD_REQUEST)
        return Response(datos_del_documento(tipo, documento))


class ArchivoDelDocumentoView(VistaDeConjunto):
    """El PDF vigente de un tipo. Quien puede verlo puede bajarlo (D1 a); la descarga se audita."""

    def get(self, request, tipo):
        exigir_permiso(request, "documento.ver", "documento.subir", "documento.descargar")
        documento = servicios.vigente(tipo, con_contenido=True)
        if documento is None:
            raise NotFound()
        servicios.registrar_descarga(request.user.persona, documento, archivada=False)
        return pdf(documento, tipo)


class VersionesView(VistaDeConjunto):
    """Todas las versiones de un tipo, la vigente primero. Solo con `documento.descargar`."""

    def get(self, request, tipo):
        exigir_permiso(request, "documento.descargar")
        lista = servicios.versiones(tipo)
        for posicion, documento in enumerate(lista):
            documento.vigente = posicion == 0
        return Response(VersionSerializer(lista, many=True).data)


class ArchivoDeVersionView(VistaDeConjunto):
    """El PDF de una versión, vigente o archivada. Solo con `documento.descargar`; se audita."""

    def get(self, request, tipo, version_id):
        exigir_permiso(request, "documento.descargar")
        documento = servicios.version(tipo, version_id, con_contenido=True)
        if documento is None:
            raise NotFound()
        actual = servicios.vigente(tipo)
        servicios.registrar_descarga(request.user.persona, documento, archivada=documento.id != actual.id)
        return pdf(documento, tipo)
