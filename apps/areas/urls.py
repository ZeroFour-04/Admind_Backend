from django.urls import path

from apps.areas.views import AreasView, DesactivarAreaView, DetalleDeAreaView, ReporteOcupacionView

urlpatterns = [
    path("", AreasView.as_view(), name="areas"),
    path("reportes/uso.pdf", ReporteOcupacionView.as_view(), name="reporte-ocupacion"),
    path("<uuid:area_id>/", DetalleDeAreaView.as_view(), name="area-detalle"),
    path("<uuid:area_id>/desactivar/", DesactivarAreaView.as_view(), name="area-desactivar"),
]
