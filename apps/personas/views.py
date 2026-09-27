"""Búsqueda por documento y vinculación al conjunto activo (HU-07).

Las dos van por POST: el documento no viaja en la URL ni queda en los logs (maestro §5.2, plan P4).
"""
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from apps.comun.aislamiento.vistas import VistaDeConjunto
from apps.permisos.servicios import RolYaAsignado
from apps.permisos.views import exigir_permiso
from apps.personas import servicios
from apps.personas.serializers import BuscarPersonaSerializer, VincularPersonaSerializer


class BuscarPersonaView(VistaDeConjunto):
    def post(self, request):
        exigir_permiso(request, "persona.buscar")
        datos = BuscarPersonaSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        try:
            persona = servicios.buscar(request.user.persona, **datos.validated_data)
        except servicios.LimiteDeBusquedas:
            return Response(
                {"detail": "Hiciste demasiadas búsquedas. Espera un rato e intenta de nuevo."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        if persona is None:
            return Response({"encontrada": False})
        return Response(
            {"encontrada": True, "persona": servicios.resumen(persona, request.auth.conjunto_activo_id)}
        )


class VincularPersonaView(VistaDeConjunto):
    def post(self, request):
        exigir_permiso(request, "persona.vincular")
        datos = VincularPersonaSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        conjunto_id = request.auth.conjunto_activo_id
        try:
            persona = servicios.vincular(
                request.user.persona, datos.validated_data["persona"], datos.validated_data["rol"], conjunto_id
            )
        except servicios.PersonaNoEncontrada:
            raise NotFound()
        except RolYaAsignado:
            return Response(
                {"detail": "Esta persona ya tiene ese rol en el conjunto."}, status=status.HTTP_409_CONFLICT
            )
        return Response(servicios.resumen(persona, conjunto_id), status=status.HTTP_201_CREATED)
