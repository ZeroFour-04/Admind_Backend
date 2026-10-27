"""Consulta y edición del horario de atención de citas (HU-31)."""
from rest_framework.response import Response
from rest_framework import status

from apps.citas import servicios
from apps.citas.serializers import (
    AgendarCitaSerializer,
    CitaAdministracionSerializer,
    CitaSerializer,
    DisponibilidadSerializer,
    FranjaCitaSerializer,
    HorarioDeAtencionSerializer,
)
from apps.comun.aislamiento.vistas import VistaDeConjunto
from apps.permisos.views import exigir_permiso


MENSAJE_FRANJA_INVALIDA = "La fecha y la hora deben corresponder a una franja futura del horario de atención."
MENSAJE_FRANJA_OCUPADA = "Esa franja ya fue agendada. Elige otra."
MENSAJE_CITA_EXISTENTE = "Ya tienes una cita futura agendada."


class HorarioDeAtencionView(VistaDeConjunto):
    def get(self, request):
        exigir_permiso(request, "cita.gestionar_horario", "cita.agendar_propia")
        return Response(servicios.horario_actual(request.auth.conjunto_activo_id))

    def put(self, request):
        exigir_permiso(request, "cita.gestionar_horario")
        entrada = HorarioDeAtencionSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        horario = servicios.guardar_horario(
            request.user.persona,
            request.auth.conjunto_activo_id,
            entrada.validated_data["dias"],
        )
        return Response(horario)


class AgendaDeCitasView(VistaDeConjunto):
    def get(self, request):
        exigir_permiso(request, "cita.gestionar_horario", "cita.agendar_propia")
        entrada = DisponibilidadSerializer(data=request.query_params)
        entrada.is_valid(raise_exception=True)
        fecha = entrada.validated_data.get("fecha")
        resultado = servicios.disponibilidad(
            request.user.persona,
            request.auth.conjunto_activo_id,
            fecha,
        )
        return Response({
            "horario": resultado["horario"],
            "franjas": FranjaCitaSerializer(resultado["franjas"], many=True).data,
            "cita_propia": CitaSerializer(resultado["cita_propia"]).data if resultado["cita_propia"] else None,
        })

    def post(self, request):
        exigir_permiso(request, "cita.agendar_propia")
        entrada = AgendarCitaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            cita = servicios.agendar(
                request.user.persona,
                request.auth.conjunto_activo_id,
                entrada.validated_data["fecha"],
                entrada.validated_data["hora_inicio"],
            )
        except servicios.FranjaDeCitaInvalida:
            return Response({"detail": MENSAJE_FRANJA_INVALIDA}, status=status.HTTP_400_BAD_REQUEST)
        except servicios.FranjaDeCitaOcupada:
            return Response({"detail": MENSAJE_FRANJA_OCUPADA}, status=status.HTTP_409_CONFLICT)
        except servicios.CitaActivaExistente:
            return Response({"detail": MENSAJE_CITA_EXISTENTE}, status=status.HTTP_409_CONFLICT)
        return Response(CitaSerializer(cita).data, status=status.HTTP_201_CREATED)


class CitasDeAdministracionView(VistaDeConjunto):
    def get(self, request):
        exigir_permiso(request, "cita.ver_todas")
        citas = servicios.citas_para_administracion(request.auth.conjunto_activo_id)
        return Response(CitaAdministracionSerializer(citas, many=True).data)
