"""Parqueaderos del conjunto activo (HU-28) y su asignación a una vivienda (HU-34). Cada vista valida, exige su permiso y llama al servicio."""
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from apps.comun.aislamiento.vistas import VistaDeConjunto
from apps.parqueaderos import servicios
from apps.parqueaderos.serializers import (
    AsignacionSerializer,
    AsignarParqueaderoSerializer,
    ConsultarParqueaderosSerializer,
    CrearParqueaderoSerializer,
    MiParqueaderoSerializer,
    ParqueaderoSerializer,
    ResultadoDeAsignacionSerializer,
)
from apps.permisos.views import exigir_permiso

MENSAJE_CODIGO_REPETIDO = {"codigo": ["Ya existe un parqueadero con ese código en el conjunto."]}
MENSAJE_OCUPADO = {"detail": "Este parqueadero está ocupado por una visita: registra primero su salida."}
MENSAJE_ASIGNADO = {"detail": "Este parqueadero está asignado a una vivienda: libéralo antes de retirarlo."}
MENSAJE_MISMA_VIVIENDA = {"detail": "Este parqueadero ya está asignado a esa vivienda."}
MENSAJE_SIN_ASIGNAR = {"detail": "Este parqueadero ya estaba sin asignar."}


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
        except servicios.ParqueaderoAsignado:
            return Response(MENSAJE_ASIGNADO, status=status.HTTP_409_CONFLICT)
        return Response(ParqueaderoSerializer(parqueadero).data)


class AsignacionView(VistaDeConjunto):
    """Asigna el puesto a una vivienda; si ya era de otra, la reasigna. La respuesta dice cuál fue."""

    def post(self, request, parqueadero_id):
        exigir_permiso(request, "parqueadero.asignar")
        datos = AsignarParqueaderoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        try:
            asignacion, reasignada = servicios.asignar(request.user.persona, parqueadero_id, datos.validated_data["unidad"])
        except servicios.ParqueaderoNoEncontrado:
            raise NotFound()
        except servicios.UnidadNoEncontrada:
            return Response({"unidad": ["No existe esa vivienda en el conjunto."]}, status=status.HTTP_400_BAD_REQUEST)
        except servicios.YaAsignadoAEsaUnidad:
            return Response(MENSAJE_MISMA_VIVIENDA, status=status.HTTP_409_CONFLICT)
        except servicios.TopeDeVehiculosAlcanzado as error:
            return Response({"detail": error.mensaje}, status=status.HTTP_409_CONFLICT)
        asignacion.reasignada = reasignada
        return Response(
            ResultadoDeAsignacionSerializer(asignacion).data,
            status=status.HTTP_200_OK if reasignada else status.HTTP_201_CREATED,
        )


class LiberacionView(VistaDeConjunto):
    """Cierra la asignación vigente sin darla a otra vivienda. Nunca por mora: la ruta no pregunta por ella."""

    def post(self, request, parqueadero_id):
        exigir_permiso(request, "parqueadero.asignar")
        try:
            cerrada = servicios.liberar(request.user.persona, parqueadero_id)
        except servicios.ParqueaderoNoEncontrado:
            raise NotFound()
        except servicios.SinAsignacionVigente:
            return Response(MENSAJE_SIN_ASIGNAR, status=status.HTTP_409_CONFLICT)
        return Response(AsignacionSerializer(cerrada).data)


class HistorialDeAsignacionesView(VistaDeConjunto):
    def get(self, request, parqueadero_id):
        exigir_permiso(request, "parqueadero.ver", "parqueadero.asignar")
        try:
            _, asignaciones = servicios.historial(parqueadero_id)
        except servicios.ParqueaderoNoEncontrado:
            raise NotFound()
        return Response(AsignacionSerializer(asignaciones, many=True).data)


class MisParqueaderosView(VistaDeConjunto):
    """Los puestos de las viviendas de quien pregunta. Sin permiso: cada persona ve solo los suyos."""

    def get(self, request):
        return Response(MiParqueaderoSerializer(servicios.mios(request.user.persona), many=True).data)
