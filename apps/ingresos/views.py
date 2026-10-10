"""Ingreso a zonas con aforo del conjunto activo. Cada vista valida, exige su permiso y llama al servicio (plan P16).

Las vistas piden el permiso y nada más: no revisan el rol por nombre. Qué ve cada quien lo decide el permiso.
"""
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from apps.comun.aislamiento.vistas import VistaDeConjunto
from apps.ingresos import servicios
from apps.ingresos.serializers import (
    BuscarResidenteSerializer,
    ConsultarIngresosSerializer,
    IngresoSerializer,
    RegistrarIngresoSerializer,
    ResidenteSerializer,
    ZonaSerializer,
)
from apps.permisos.servicios import tiene_permiso
from apps.permisos.views import exigir_permiso

# Los cupos son un conteo, sin nombres: los ve quien consulta zonas o quien trabaja con ingresos (plan P17).
PERMISOS_DE_CUPOS = ("area.ver", "area.gestionar", "ingreso.registrar", "ingreso.ver_historico")
MENSAJE_YA_SALIO = {"detail": "Esta persona ya salió."}
MENSAJE_SIN_INGRESO = {"detail": "Esta zona no es con ingreso."}


class ZonasView(VistaDeConjunto):
    def get(self, request):
        exigir_permiso(request, *PERMISOS_DE_CUPOS)
        return Response(ZonaSerializer(servicios.zonas(), many=True).data)


class BuscarResidenteView(VistaDeConjunto):
    def post(self, request):
        exigir_permiso(request, "ingreso.registrar")
        datos = BuscarResidenteSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        encontrados = servicios.buscar_residente(request.user.persona, datos.validated_data["numero_documento"])
        if not encontrados:
            # Exista o no la persona en otro conjunto: la respuesta es la misma.
            raise NotFound()
        return Response(ResidenteSerializer(encontrados, many=True).data)


class IngresosView(VistaDeConjunto):
    def get(self, request):
        """Con `ingreso.registrar`, quién está adentro y a quién se le cumplió el tiempo hoy; con `ingreso.ver_historico`, el historial."""
        exigir_permiso(request, "ingreso.registrar", "ingreso.ver_historico")
        persona, conjunto_id = request.user.persona, request.auth.conjunto_activo_id
        respuesta = {}
        if tiene_permiso(persona, conjunto_id, "ingreso.registrar"):
            respuesta["adentro"] = IngresoSerializer(servicios.adentro(), many=True).data
            respuesta["vencidos_hoy"] = IngresoSerializer(servicios.vencidos_de_hoy(), many=True).data
        if tiene_permiso(persona, conjunto_id, "ingreso.ver_historico"):
            consulta = ConsultarIngresosSerializer(data=request.query_params)
            consulta.is_valid(raise_exception=True)
            historial = servicios.historial(consulta.validated_data.get("area"), consulta.validated_data.get("fecha"))
            respuesta["historial"] = IngresoSerializer(historial, many=True).data
        return Response(respuesta)

    def post(self, request):
        exigir_permiso(request, "ingreso.registrar")
        datos = RegistrarIngresoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        campos = datos.validated_data
        try:
            ingreso = servicios.registrar(
                request.user.persona, campos["area"], campos["persona"], campos["unidad"], campos["acompanantes"]
            )
        except (servicios.AreaNoEncontrada, servicios.UnidadNoEncontrada, servicios.ResidenteNoEncontrado):
            raise NotFound() from None
        except servicios.AreaSinIngreso:
            return Response(MENSAJE_SIN_INGRESO, status=status.HTTP_409_CONFLICT)
        except servicios.IncumpleReglas as error:
            return Response({"motivos": error.motivos}, status=status.HTTP_400_BAD_REQUEST)
        return Response(IngresoSerializer(ingreso).data, status=status.HTTP_201_CREATED)


class SalidaView(VistaDeConjunto):
    def post(self, request, ingreso_id):
        exigir_permiso(request, "ingreso.registrar")
        try:
            ingreso = servicios.registrar_salida(request.user.persona, ingreso_id)
        except servicios.IngresoNoEncontrado:
            raise NotFound() from None
        except servicios.YaSalio:
            return Response(MENSAJE_YA_SALIO, status=status.HTTP_409_CONFLICT)
        return Response(IngresoSerializer(ingreso).data)
