from django.http import HttpResponse
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from apps.casos import servicios
from apps.casos.serializers import CasoSerializer, CrearCasoSerializer, RechazarCasoSerializer
from apps.comun.aislamiento.vistas import VistaDeConjunto
from apps.permisos.servicios import es_superusuario
from apps.permisos.servicios import permisos_efectivos
from apps.permisos.views import exigir_permiso

TIPOS_DE_FOTO = {"image/png", "image/jpeg", "image/webp"}


class CasosView(VistaDeConjunto):
    def get(self, request):
        exigir_permiso(request, "caso.crear", "caso.ver_todos", "caso.responder")
        permisos = permisos_efectivos(request.user.persona, request.auth.conjunto_activo_id)
        if es_superusuario(request.user.persona):
            casos = servicios.casos_de_todo_el_conjunto()
        elif "caso.responder" in permisos:
            casos = servicios.casos_redirigidos_a_administracion()
        else:
            casos = servicios.casos_visibles(request.user.persona, "caso.ver_todos" in permisos)
        return Response(CasoSerializer(casos, many=True).data)

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


class GestionarCasoView(VistaDeConjunto):
    def post(self, request, caso_id, accion):
        exigir_permiso(request, "caso.gestionar")
        if accion == "rechazar":
            datos = RechazarCasoSerializer(data=request.data)
            datos.is_valid(raise_exception=True)
            try:
                caso = servicios.rechazar(caso_id, datos.validated_data["motivo"])
            except servicios.CasoNoGestionable:
                return Response(
                    {"detail": "El caso ya fue gestionado."},
                    status=status.HTTP_409_CONFLICT,
                )
        else:
            try:
                caso = servicios.redirigir(caso_id)
            except servicios.CasoNoGestionable:
                return Response(
                    {"detail": "El caso ya fue gestionado."},
                    status=status.HTTP_409_CONFLICT,
                )
        if caso is None:
            raise NotFound()
        return Response(CasoSerializer(caso).data)


class FotoDeCasoView(VistaDeConjunto):
    def get(self, request, caso_id, foto_id):
        exigir_permiso(request, "caso.crear", "caso.ver_todos")
        puede_ver_todos = "caso.ver_todos" in permisos_efectivos(request.user.persona, request.auth.conjunto_activo_id)
        foto = servicios.foto_visible(request.user.persona, caso_id, foto_id, puede_ver_todos)
        if foto is None or foto.tipo not in TIPOS_DE_FOTO:
            raise NotFound()
        return HttpResponse(bytes(foto.contenido), content_type=foto.tipo)
