"""Parqueaderos del conjunto activo (HU-28). Cada vista valida, exige su permiso y llama al servicio."""
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from apps.comun.aislamiento.vistas import VistaDeConjunto
from apps.parqueaderos import servicios
from apps.parqueaderos.serializers import (
    ConsultarParqueaderosSerializer,
    CrearParqueaderoSerializer,
    ParqueaderoSerializer,
)
from apps.permisos.views import exigir_permiso

MENSAJE_CODIGO_REPETIDO = {"codigo": ["Ya existe un parqueadero con ese código en el conjunto."]}
MENSAJE_OCUPADO = {"detail": "Este parqueadero está ocupado por una visita: registra primero su salida."}


class ParqueaderosView(VistaDeConjunto):
    def get(self, request):
        # Vigilancia necesita la lista de libres para elegir puesto al registrar una visita.
        exigir_permiso(request, "parqueadero.ver", "parqueadero.gestionar", "visitante.registrar")
        consulta = ConsultarParqueaderosSerializer(data=request.query_params)
        consulta.is_valid(raise_exception=True)
        lista = servicios.parqueaderos(consulta.validated_data.get("tipo"), consulta.validated_data["libres"])
        return Response(ParqueaderoSerializer(lista, many=True).data)

    def post(self, request):
        exigir_permiso(request, "parqueadero.gestionar")
        datos = CrearParqueaderoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        try:
            parqueadero = servicios.crear(request.user.persona, **datos.validated_data)
        except servicios.CodigoRepetido:
            return Response(MENSAJE_CODIGO_REPETIDO, status=status.HTTP_400_BAD_REQUEST)
        return Response(ParqueaderoSerializer(parqueadero).data, status=status.HTTP_201_CREATED)


class DesactivarParqueaderoView(VistaDeConjunto):
    def post(self, request, parqueadero_id):
        exigir_permiso(request, "parqueadero.gestionar")
        try:
            parqueadero = servicios.desactivar(request.user.persona, parqueadero_id)
        except servicios.ParqueaderoNoEncontrado:
            raise NotFound()
        except servicios.ParqueaderoOcupado:
            return Response(MENSAJE_OCUPADO, status=status.HTTP_409_CONFLICT)
        return Response(ParqueaderoSerializer(parqueadero).data)
