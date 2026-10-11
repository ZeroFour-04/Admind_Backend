"""Pago de la administración (HU-35). Cada vista valida, exige su permiso y llama al servicio.

Ver y actuar son permisos distintos: `pago.ver` consulta la tabla, `pago.confirmar` pone el check y
`pago.reportar` sube el comprobante de una vivienda propia.
"""
from django.http import HttpResponse
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from apps.comun.aislamiento.vistas import VistaDeConjunto
from apps.comun.archivos import comprobantes
from apps.pagos import periodos, servicios
from apps.pagos.serializers import (
    ConfirmacionSerializer,
    ConsultarPagosSerializer,
    ReportarPagoSerializer,
    datos_del_pago,
    fila_de_gestion,
    vivienda_del_residente,
)
from apps.permisos.views import exigir_permiso, tiene_permiso_en_conjunto

MENSAJE_PERIODO = "El periodo va como AAAA-MM, por ejemplo 2026-10."
EXTENSION_POR_TIPO = {"application/pdf": "pdf", "image/png": "png", "image/jpeg": "jpg"}


def periodo_pedido(texto, por_defecto_hoy=False):
    """El día 1 del mes pedido. Un periodo mal escrito responde 400 bajo `periodo`."""
    if not texto and por_defecto_hoy:
        return periodos.actual()
    try:
        return periodos.periodo_de(texto)
    except ValueError as error:
        raise ValidationError({"periodo": [str(error) or MENSAJE_PERIODO]}) from error


class PagosDeAdministracionView(VistaDeConjunto):
    def get(self, request):
        """La tabla del mes: una fila por vivienda, con el buscador en el servidor."""
        exigir_permiso(request, "pago.ver")
        consulta = ConsultarPagosSerializer(data=request.query_params)
        consulta.is_valid(raise_exception=True)
        periodo = periodo_pedido(consulta.validated_data["periodo"], por_defecto_hoy=True)
        filas = servicios.filas_del_periodo(periodo, consulta.validated_data["buscar"])
        return Response({"periodo": periodos.texto_de(periodo), "filas": [fila_de_gestion(fila) for fila in filas]})


class ConfirmacionView(VistaDeConjunto):
    def post(self, request, unidad_id, periodo):
        """Pone o quita el check. Solo Administración: Secretaría consulta y no marca."""
        exigir_permiso(request, "pago.confirmar")
        datos = ConfirmacionSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        mes = periodo_pedido(periodo)
        try:
            servicios.confirmar(request.user.persona, unidad_id, mes, datos.validated_data["confirmado"])
            fila = servicios.fila_de(unidad_id, mes)
        except servicios.UnidadNoEncontrada:
            raise NotFound()
        return Response(fila_de_gestion(fila))


class ReportesView(VistaDeConjunto):
    def post(self, request):
        """El residente sube el comprobante del mes de una vivienda suya. No confirma nada."""
        exigir_permiso(request, "pago.reportar")
        datos = ReportarPagoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        campos = datos.validated_data
        mes = periodo_pedido(campos["periodo"])
        archivo = campos["archivo"]
        # Se lee un byte más del límite: basta para saber que se pasa, sin cargar un archivo enorme.
        contenido = archivo.read(comprobantes.TAMANO_MAXIMO_DE_COMPROBANTE + 1)
        try:
            servicios.reportar(request.user.persona, campos["unidad"], mes, archivo.name, contenido)
        except servicios.UnidadNoEncontrada:
            raise NotFound()
        except servicios.PeriodoNoPermitido:
            return Response(
                {"periodo": ["Solo se reportan los últimos 12 meses y el mes siguiente."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except servicios.ComprobanteInvalido as error:
            return Response({"archivo": [error.mensaje]}, status=status.HTTP_400_BAD_REQUEST)
        except servicios.YaConfirmado:
            return Response(
                {"detail": "Ese mes ya está confirmado por la administración."}, status=status.HTTP_409_CONFLICT
            )
        fila = servicios.fila_de(campos["unidad"], mes)
        reportado = {
            "unidad": {"id": fila["unidad"].id, "nombre": fila["unidad"].nombre},
            "periodo": periodos.texto_de(mes),
            **datos_del_pago(fila["pago"]),
        }
        return Response(reportado, status=status.HTTP_201_CREATED)


class MisPagosView(VistaDeConjunto):
    def get(self, request):
        """Por cada vivienda de la persona, sus últimos 6 periodos con su estado."""
        # `pago.ver` entra para que quien gestiona y no tiene viviendas reciba una lista vacía, no un 403.
        exigir_permiso(request, "pago.reportar", "pago.ver")
        viviendas = servicios.mis_pagos(request.user.persona)
        return Response([vivienda_del_residente(vivienda) for vivienda in viviendas])


class ComprobanteView(VistaDeConjunto):
    def get(self, request, comprobante_id):
        """El archivo, solo por esta ruta. Quien no puede verlo recibe 404, no 403."""
        exigir_permiso(request, "pago.ver", "pago.reportar")
        comprobante = servicios.comprobante_para(
            request.user.persona, tiene_permiso_en_conjunto(request, "pago.ver"), comprobante_id
        )
        if comprobante is None:
            raise NotFound()
        respuesta = HttpResponse(bytes(comprobante.contenido), content_type=comprobante.tipo)
        # El nombre de la cabecera se fabrica aquí: el que escribió quien subió el archivo no viaja en ella.
        extension = EXTENSION_POR_TIPO.get(comprobante.tipo, "bin")
        respuesta["Content-Disposition"] = f'inline; filename="comprobante-{comprobante.huella[:8]}.{extension}"'
        respuesta["X-Content-Type-Options"] = "nosniff"
        return respuesta
