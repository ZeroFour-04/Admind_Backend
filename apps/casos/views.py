"""Casos del conjunto activo (HU-29). Cada vista valida, exige su permiso y llama al servicio."""
from django.http import HttpResponse
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from apps.casos import servicios
from apps.casos.serializers import (
    CasoParaGestionSerializer,
    CasoSerializer,
    ConsultarCasosSerializer,
    CrearCasoSerializer,
    DescartarCasoSerializer,
    PriorizarCasoSerializer,
    RechazarCasoSerializer,
    RedirigirCasoSerializer,
    ResponderCasoSerializer,
)
from apps.comun.aislamiento.vistas import VistaDeConjunto
from apps.permisos.views import exigir_permiso, tiene_permiso_en_conjunto

TIPOS_DE_FOTO = {"image/png", "image/jpeg", "image/webp"}
MENSAJE_YA_GESTIONADO = {"detail": "El caso ya fue gestionado."}


def ve_todos(request):
    """Gestión ve todos los casos del conjunto; quien solo los abre, los suyos."""
    return tiene_permiso_en_conjunto(request, "caso.ver_todos")


def serializar(request, caso):
    serializer = CasoParaGestionSerializer if ve_todos(request) else CasoSerializer
    return serializer(caso).data


class CasosView(VistaDeConjunto):
    def get(self, request):
        exigir_permiso(request, "caso.crear", "caso.ver_todos")
        if not ve_todos(request):
            return Response(CasoSerializer(servicios.casos_de(request.user.persona), many=True).data)
        consulta = ConsultarCasosSerializer(data=request.query_params)
        consulta.is_valid(raise_exception=True)
        casos = servicios.casos_para_bandeja(**consulta.validated_data)
        if tiene_permiso_en_conjunto(request, "caso.responder") and not tiene_permiso_en_conjunto(request, "caso.gestionar"):
            casos = casos.filter(estado=servicios.EstadoCaso.REDIRIGIDO)
        return Response(CasoParaGestionSerializer(casos, many=True).data)

    def post(self, request):
        exigir_permiso(request, "caso.crear")
        datos = CrearCasoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        campos = dict(datos.validated_data)
        foto = campos.pop("foto", None)
        contenido = foto.read(servicios.TAMANO_MAXIMO_FOTO + 1) if foto else None
        try:
            caso = servicios.crear(
                request.user.persona,
                titulo=campos["titulo"],
                cuerpo=campos["caso"],
                foto=contenido,
            )
        except servicios.FotoInvalida as error:
            return Response({"foto": [error.mensaje]}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CasoSerializer(caso).data, status=status.HTTP_201_CREATED)


class DetalleDeCasoView(VistaDeConjunto):
    def get(self, request, caso_id):
        """El de otra persona o de otro conjunto responde 404: no se confirma que existe."""
        exigir_permiso(request, "caso.crear", "caso.ver_todos")
        persona = None if ve_todos(request) else request.user.persona
        caso = servicios.detalle(caso_id, persona)
        if caso is None:
            raise NotFound()
        if (
            tiene_permiso_en_conjunto(request, "caso.responder")
            and not tiene_permiso_en_conjunto(request, "caso.gestionar")
            and caso.estado != servicios.EstadoCaso.REDIRIGIDO
        ):
            raise NotFound()
        return Response(serializar(request, caso))


class AccionSobreCasoView(VistaDeConjunto):
    """Una transición del caso. Cada subclase dice quién puede, qué datos pide y qué operación es."""

    permisos = ()
    serializer = None

    def operar(self, actor, caso_id, datos):
        raise NotImplementedError

    def post(self, request, caso_id):
        exigir_permiso(request, *self.permisos)
        datos = {}
        if self.serializer is not None:
            entrada = self.serializer(data=request.data)
            entrada.is_valid(raise_exception=True)
            datos = entrada.validated_data
        try:
            caso = self.operar(request.user.persona, caso_id, datos)
        except servicios.CasoNoEncontrado:
            raise NotFound()
        except servicios.CasoNoGestionable:
            return Response(MENSAJE_YA_GESTIONADO, status=status.HTTP_409_CONFLICT)
        return Response(serializar(request, caso))


class TomarCasoView(AccionSobreCasoView):
    permisos = ("caso.gestionar", "caso.responder")

    def operar(self, actor, caso_id, datos):
        return servicios.tomar(actor, caso_id)


class PriorizarCasoView(AccionSobreCasoView):
    permisos = ("solicitud.priorizar",)
    serializer = PriorizarCasoSerializer

    def operar(self, actor, caso_id, datos):
        return servicios.priorizar(actor, caso_id, datos["prioridad"], datos["justificacion"])


class RedirigirCasoView(AccionSobreCasoView):
    permisos = ("caso.gestionar",)
    serializer = RedirigirCasoSerializer

    def operar(self, actor, caso_id, datos):
        return servicios.redirigir(actor, caso_id, datos["nota"])


class DescartarCasoView(AccionSobreCasoView):
    """La Secretaría cierra por causal formal. Responder de fondo no le corresponde."""

    permisos = ("caso.gestionar",)
    serializer = DescartarCasoSerializer

    def operar(self, actor, caso_id, datos):
        return servicios.descartar(actor, caso_id, datos["causal"], datos["motivo"])


class ResponderCasoView(AccionSobreCasoView):
    permisos = ("caso.responder",)
    serializer = ResponderCasoSerializer

    def operar(self, actor, caso_id, datos):
        return servicios.responder(actor, caso_id, datos["respuesta"])


class RechazarCasoView(AccionSobreCasoView):
    permisos = ("caso.responder",)
    serializer = RechazarCasoSerializer

    def operar(self, actor, caso_id, datos):
        return servicios.rechazar(actor, caso_id, datos["motivo"])


class FotoDeCasoView(VistaDeConjunto):
    def get(self, request, caso_id, foto_id):
        exigir_permiso(request, "caso.crear", "caso.ver_todos")
        foto = servicios.foto_visible(request.user.persona, caso_id, foto_id, ve_todos(request))
        if foto is None or foto.tipo not in TIPOS_DE_FOTO:
            raise NotFound()
        if (
            tiene_permiso_en_conjunto(request, "caso.responder")
            and not tiene_permiso_en_conjunto(request, "caso.gestionar")
            and foto.caso.estado != servicios.EstadoCaso.REDIRIGIDO
        ):
            raise NotFound()
        return HttpResponse(bytes(foto.contenido), content_type=foto.tipo)
