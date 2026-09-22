"""Anuncios del conjunto activo (HU-25). Cada vista valida, exige su permiso y llama al servicio."""
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response

from apps.anuncios import servicios
from apps.anuncios.serializers import AnuncioSerializer, EditarAnuncioSerializer, PublicarAnuncioSerializer
from apps.comun.aislamiento.vistas import VistaDeConjunto
from apps.permisos.servicios import permisos_efectivos
from apps.permisos.views import exigir_permiso


def contexto(request):
    persona = request.user.persona
    return {"persona": persona, "permisos": permisos_efectivos(persona, request.auth.conjunto_activo_id)}


class AnunciosView(VistaDeConjunto):
    def get(self, request):
        anuncios = servicios.tablon(request.user.persona, request.auth.conjunto_activo_id)
        return Response(AnuncioSerializer(anuncios, many=True, context=contexto(request)).data)

    def post(self, request):
        # El permiso depende del alcance que se pide y se revisa antes que los demás datos.
        alcance = request.data.get("alcance") if hasattr(request.data, "get") else None
        permiso = servicios.PERMISO_POR_ALCANCE.get(alcance) if isinstance(alcance, str) else None
        exigir_permiso(request, permiso or "anuncio.publicar")
        datos = PublicarAnuncioSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        try:
            anuncio = servicios.publicar(request.user.persona, **datos.validated_data)
        except servicios.UnidadNoEncontrada:
            return Response(
                {"unidad": ["Esa vivienda no existe en este conjunto."]}, status=status.HTTP_400_BAD_REQUEST
            )
        return Response(AnuncioSerializer(anuncio, context=contexto(request)).data, status=status.HTTP_201_CREATED)


class DetalleDeAnuncioView(VistaDeConjunto):
    def anuncio_visible(self, request, anuncio_id):
        """Un anuncio que la persona no puede ver responde 404, igual que uno de otro conjunto."""
        anuncio = servicios.tablon(request.user.persona, request.auth.conjunto_activo_id).filter(pk=anuncio_id).first()
        if anuncio is None:
            raise NotFound()
        return anuncio

    def get(self, request, anuncio_id):
        anuncio = self.anuncio_visible(request, anuncio_id)
        return Response(AnuncioSerializer(anuncio, context=contexto(request)).data)

    def patch(self, request, anuncio_id):
        anuncio = self.anuncio_visible(request, anuncio_id)
        datos_de_permiso = contexto(request)
        if not servicios.puede_editar(datos_de_permiso["persona"], datos_de_permiso["permisos"], anuncio):
            raise PermissionDenied("Solo quien publicó el anuncio puede editarlo.")
        datos = EditarAnuncioSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        servicios.editar(anuncio, **datos.validated_data)
        return Response(AnuncioSerializer(anuncio, context=datos_de_permiso).data)
