from django.urls import path

from apps.reportes.views import ReportePagosView, ReporteZonasView

urlpatterns = [
    path("zonas.pdf", ReporteZonasView.as_view(), name="reporte-zonas"),
    path("pagos.xlsx", ReportePagosView.as_view(), name="reporte-pagos"),
]
