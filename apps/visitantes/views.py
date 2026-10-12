"""Visitantes del conjunto activo (HU-27, HU-28). Cada vista valida, exige su permiso y llama al servicio.

Las reglas —solo Vigilancia registra, el parqueadero libre, la salida— viven en `servicios.py`.
"""
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response

from apps.comun.aislamiento.vistas import VistaDeConjunto
from apps.permisos.servicios import tiene_permiso
from apps.permisos.views import exigir_permiso
from apps.visitantes import servicios
from apps.visitantes.serializers import RegistrarVisitanteSerializer, VisitanteSerializer

MENSAJE_SOLO_VIGILANCIA = "Solo Vigilancia puede registrar visitantes."
MENSAJE_SALIDA_SOLO_VIGILANCIA = "Solo Vigilancia puede registrar la salida de los visitantes."


class VisitantesView(VistaDeConjunto):
    def get(self, request):
        exigir_permiso(request, "visitante.registrar", "visitante.ver_historico")
        solo_de_hoy = not tiene_permiso(
            request.user.persona, request.auth.conjunto_activo_id, "visitante.ver_historico"
        )
        busqueda = request.GET.get("q") or request.GET.get("buscar") or ""
        return Response(VisitanteSerializer(servicios.visitantes_para(solo_de_hoy, buscar=busqueda), many=True).data)

    def post(self, request):
        exigir_permiso(request, "visitante.registrar")
        datos = RegistrarVisitanteSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        campos = datos.validated_data
        try:
            visitante = servicios.registrar_ingreso(
                request.user.persona,
                request.auth.conjunto_activo_id,
                nombre=campos["nombre"],
                cedula=campos["cedula"],
                placa_vehiculo=campos["placa_vehiculo"],
                tipo_vehiculo=campos["tipo_vehiculo"],
                unidad_id=campos["apartamento_visitado"],
                parqueadero_id=campos["parqueadero"],
            )
        except servicios.SoloVigilancia:
            raise PermissionDenied(MENSAJE_SOLO_VIGILANCIA)
        except servicios.UnidadNoEncontrada:
            raise NotFound("El apartamento visitado no existe en el conjunto activo.")
        except servicios.ParqueaderoNoDisponible:
            return Response(
                {"parqueadero": ["Ese parqueadero no es de visitantes o ya no existe."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except servicios.ParqueaderoOcupado:
            return Response(
                {"detail": "Ese parqueadero se acaba de ocupar. Elige otro o registra la visita sin parqueadero."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(VisitanteSerializer(visitante).data, status=status.HTTP_201_CREATED)


class SalidaDeVisitanteView(VistaDeConjunto):
    def post(self, request, visitante_id):
        """Registra la salida. Si la visita tenía parqueadero, queda libre al instante."""
        exigir_permiso(request, "visitante.registrar")
        try:
            visitante = servicios.registrar_salida(
                request.user.persona, request.auth.conjunto_activo_id, visitante_id
            )
        except servicios.SoloVigilancia:
            raise PermissionDenied(MENSAJE_SALIDA_SOLO_VIGILANCIA)
        except servicios.VisitanteNoEncontrado:
            raise NotFound()
        except servicios.YaSalio:
            return Response({"detail": "Este visitante ya salió."}, status=status.HTTP_409_CONFLICT)
        return Response(VisitanteSerializer(visitante).data)
