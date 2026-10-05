from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response

from apps.comun.aislamiento.vistas import VistaDeConjunto
from apps.permisos.catalogo import Rol
from apps.permisos.models import Asignacion
from apps.permisos.servicios import tiene_permiso
from apps.permisos.views import exigir_permiso
from apps.unidades.models import Unidad
from apps.visitantes.models import Visitante
from apps.visitantes.serializers import RegistrarVisitanteSerializer, VisitanteSerializer


class VisitantesView(VistaDeConjunto):
    def get(self, request):
        exigir_permiso(request, "visitante.registrar", "visitante.ver_historico")
        visitantes = Visitante.objects.select_related("unidad").order_by("-hora_entrada")
        if not tiene_permiso(
            request.user.persona, request.auth.conjunto_activo_id, "visitante.ver_historico"
        ):
            visitantes = visitantes.filter(hora_entrada__date=timezone.localdate())
        return Response(VisitanteSerializer(visitantes, many=True).data)

    def post(self, request):
        exigir_permiso(request, "visitante.registrar")
        es_vigilancia = Asignacion.objects.vigentes().filter(
            persona=request.user.persona,
            conjunto_id=request.auth.conjunto_activo_id,
            rol=Rol.VIGILANCIA,
        ).exists()
        if not es_vigilancia:
            raise PermissionDenied("Solo Vigilancia puede registrar visitantes.")
        datos = RegistrarVisitanteSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        campos = datos.validated_data
        unidad = Unidad.objects.filter(pk=campos["apartamento_visitado"]).first()
        if unidad is None:
            raise NotFound("El apartamento visitado no existe en el conjunto activo.")

        visitante = Visitante.objects.create(
            nombre=campos["nombre"],
            cedula=campos["cedula"],
            placa_vehiculo=campos["placa_vehiculo"],
            tipo_vehiculo=campos["tipo_vehiculo"],
            unidad=unidad,
        )
        return Response(VisitanteSerializer(visitante).data, status=status.HTTP_201_CREATED)
