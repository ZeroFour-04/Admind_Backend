"""Registro de infracciones del conjunto activo (HU-30). Cada vista valida, exige su permiso y llama al servicio.

No hay `PUT`, `PATCH` ni `DELETE`: un registro no se edita ni se borra; se cierra o, si es un error, se anula.
Todos los permisos son sensibles (segundo factor).
"""
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from apps.comun.aislamiento.vistas import VistaDeConjunto
from apps.infracciones import servicios
from apps.infracciones.serializers import (
    AnularInfraccionSerializer,
    CerrarInfraccionSerializer,
    RegistrarInfraccionSerializer,
    RegistroSerializer,
)
from apps.permisos.views import exigir_permiso

MENSAJE_SIN_DESTINATARIOS = {"unidad": ["La vivienda no tiene a quién comunicarle."]}
MENSAJE_YA_CERRADA = {"detail": "Este registro ya está cerrado."}
MENSAJE_YA_ANULADA = {"detail": "Este registro ya está anulado."}


def encontrado(registro):
    if registro is None:
        raise NotFound()
    return registro


class InfraccionesView(VistaDeConjunto):
    def get(self, request):
        exigir_permiso(request, "infraccion.ver")
        return Response(RegistroSerializer(servicios.registros(), many=True).data)

    def post(self, request):
        exigir_permiso(request, "infraccion.registrar")
        datos = RegistrarInfraccionSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        try:
            registro = servicios.registrar(
                request.user.persona,
                datos.validated_data["unidad"],
                datos.validated_data["descripcion_hecho"],
                datos.validated_data["fecha_hecho"],
                datos.validated_data["caso"],
            )
        except servicios.UnidadNoEncontrada:
            return Response({"unidad": ["No existe esa vivienda en el conjunto."]}, status=status.HTTP_400_BAD_REQUEST)
        except servicios.CasoNoEncontrado:
            return Response({"caso": ["No existe ese caso en el conjunto."]}, status=status.HTTP_400_BAD_REQUEST)
        except servicios.SinDestinatarios:
            return Response(MENSAJE_SIN_DESTINATARIOS, status=status.HTTP_400_BAD_REQUEST)
        return Response(RegistroSerializer(registro).data, status=status.HTTP_201_CREATED)


class DetalleDeInfraccionView(VistaDeConjunto):
    def get(self, request, registro_id):
        exigir_permiso(request, "infraccion.ver")
        return Response(RegistroSerializer(encontrado(servicios.detalle(registro_id))).data)


class CierreView(VistaDeConjunto):
    def post(self, request, registro_id):
        exigir_permiso(request, "infraccion.cerrar")
        datos = CerrarInfraccionSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        try:
            registro = servicios.cerrar(request.user.persona, registro_id, datos.validated_data["comentario"])
        except servicios.InfraccionNoEncontrada:
            raise NotFound()
        except servicios.YaCerrada:
            return Response(MENSAJE_YA_CERRADA, status=status.HTTP_409_CONFLICT)
        except servicios.YaAnulada:
            return Response(MENSAJE_YA_ANULADA, status=status.HTTP_409_CONFLICT)
        return Response(RegistroSerializer(registro).data)


class AnulacionView(VistaDeConjunto):
    def post(self, request, registro_id):
        exigir_permiso(request, "infraccion.anular")
        datos = AnularInfraccionSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        try:
            registro = servicios.anular(request.user.persona, registro_id, datos.validated_data["motivo"])
        except servicios.InfraccionNoEncontrada:
            raise NotFound()
        except servicios.YaAnulada:
            return Response(MENSAJE_YA_ANULADA, status=status.HTTP_409_CONFLICT)
        return Response(RegistroSerializer(registro).data)
