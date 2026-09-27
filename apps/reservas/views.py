"""Franjas y solicitudes de reserva del conjunto activo (HU-11). Cada vista valida, exige su permiso y llama al servicio."""
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from apps.areas.models import Area
from apps.comun.aislamiento.vistas import VistaDeConjunto
from apps.permisos.views import exigir_permiso
from apps.reservas import servicios
from apps.reservas.serializers import (
    ConsultarFranjasSerializer,
    DetalleDeSolicitudSerializer,
    FranjaSerializer,
    SolicitudSerializer,
    TomarBloqueoSerializer,
)

MENSAJE_NO_EN_TRAMITE = {"detail": "Esta solicitud ya no está en trámite."}


def area_del_conjunto(area_id):
    """Un área de otro conjunto, o que no existe, responde 404 sin detalle."""
    area = Area.objects.filter(pk=area_id).first()
    if area is None:
        raise NotFound()
    return area


def solicitud_propia(request, solicitud_id):
    """Solo las propias: la de otra persona o de otro conjunto responde 404."""
    solicitud = servicios.detalle(request.user.persona, solicitud_id)
    if solicitud is None:
        raise NotFound()
    return solicitud


class FranjasView(VistaDeConjunto):
    def get(self, request):
        exigir_permiso(request, "reserva.solicitar", "reserva.ver_todas")
        consulta = ConsultarFranjasSerializer(data=request.query_params)
        consulta.is_valid(raise_exception=True)
        area = area_del_conjunto(consulta.validated_data["area"])
        fecha = consulta.validated_data["fecha"]
        franjas = servicios.franjas(request.user.persona, area, fecha)
        return Response(
            {
                "area": {"id": area.id, "nombre": area.nombre},
                "fecha": fecha,
                "franjas": FranjaSerializer(franjas, many=True).data,
            }
        )


class SolicitudesView(VistaDeConjunto):
    def get(self, request):
        exigir_permiso(request, "reserva.solicitar", "reserva.ver_todas")
        return Response(SolicitudSerializer(servicios.solicitudes_de(request.user.persona), many=True).data)

    def post(self, request):
        """Toma el bloqueo de la franja: 3 minutos exclusivos para llenar y enviar la solicitud."""
        exigir_permiso(request, "reserva.solicitar")
        datos = TomarBloqueoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        campos = datos.validated_data
        area = area_del_conjunto(campos["area"])
        try:
            solicitud = servicios.tomar_bloqueo(request.user.persona, area, campos["fecha"], campos["hora_inicio"])
        except servicios.SinUnidadParaSolicitar:
            return Response(
                {"detail": "Para reservar necesitas vivir en un apartamento del conjunto."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except servicios.FranjaInvalida:
            return Response(
                {"hora_inicio": ["Esa franja no está en el horario del área o ya empezó."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except servicios.AreaNoDisponible:
            return Response(
                {"detail": "Esta área no está disponible para reservas en este momento."},
                status=status.HTTP_409_CONFLICT,
            )
        except servicios.FranjaOcupada:
            return Response(
                {"detail": "Otra persona está tramitando esta franja en este momento."},
                status=status.HTTP_409_CONFLICT,
            )
        except servicios.YaTienesUnBloqueo as bloqueo:
            return Response(
                {
                    "detail": "Ya tienes otra solicitud en trámite. Envíala o cancélala antes de tomar otra franja.",
                    "solicitud": bloqueo.solicitud_id,
                },
                status=status.HTTP_409_CONFLICT,
            )
        return Response(DetalleDeSolicitudSerializer(solicitud).data, status=status.HTTP_201_CREATED)


class DetalleDeSolicitudView(VistaDeConjunto):
    def get(self, request, solicitud_id):
        exigir_permiso(request, "reserva.solicitar", "reserva.ver_todas")
        return Response(DetalleDeSolicitudSerializer(solicitud_propia(request, solicitud_id)).data)


class LiberarSolicitudView(VistaDeConjunto):
    def post(self, request, solicitud_id):
        """Soltar el bloqueo a propósito: al cerrar o cancelar el formulario."""
        exigir_permiso(request, "reserva.solicitar")
        solicitud = solicitud_propia(request, solicitud_id)
        try:
            servicios.liberar(request.user.persona, solicitud)
        except servicios.NoEstaEnTramite:
            return Response(MENSAJE_NO_EN_TRAMITE, status=status.HTTP_409_CONFLICT)
        return Response(DetalleDeSolicitudSerializer(solicitud).data)
