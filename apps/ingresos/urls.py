from django.urls import path

from apps.ingresos.views import BuscarResidenteView, IngresosView, SalidaView, ZonasView

urlpatterns = [
    path("", IngresosView.as_view(), name="ingresos"),
    path("zonas/", ZonasView.as_view(), name="ingresos-zonas"),
    path("residentes/buscar/", BuscarResidenteView.as_view(), name="ingreso-residentes-buscar"),
    path("<uuid:ingreso_id>/salida/", SalidaView.as_view(), name="ingreso-salida"),
]
