"""Descargas de reportes del conjunto activo, disponibles solo para Administración."""
from django.http import HttpResponse
from rest_framework.exceptions import ValidationError

from apps.areas import reportes as reportes_areas
from apps.areas.serializers import RangoDeReporteSerializer
from apps.comun.aislamiento.vistas import VistaDeConjunto
from apps.pagos import periodos
from apps.pagos.models import estado_pagos
from apps.pagos.reportes import estado_de_pagos_excel
from apps.permisos.views import exigir_permiso


class ReporteZonasView(VistaDeConjunto):
    def get(self, request):
        exigir_permiso(request, "reporte.ver")
        consulta = RangoDeReporteSerializer(data=request.query_params)
        consulta.is_valid(raise_exception=True)
        contenido = reportes_areas.uso_zonas_pdf(
            request.auth.conjunto_activo,
            consulta.validated_data["desde"],
            consulta.validated_data["hasta"],
        )
        respuesta = HttpResponse(contenido, content_type="application/pdf")
        respuesta["Content-Disposition"] = 'attachment; filename="uso-zonas-comunes.pdf"'
        return respuesta


class ReportePagosView(VistaDeConjunto):
    def get(self, request):
        exigir_permiso(request, "reporte.ver")
        try:
            periodo = periodos.periodo_de(request.query_params.get("periodo"))
        except ValueError as error:
            raise ValidationError({"periodo": [str(error)]}) from error
        filas = estado_pagos(request.auth.conjunto_activo_id, periodo)
        respuesta = HttpResponse(
            estado_de_pagos_excel(request.auth.conjunto_activo, periodo, filas),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        respuesta["Content-Disposition"] = f'attachment; filename="estado-pagos-{periodos.texto_de(periodo)}.xlsx"'
        return respuesta
