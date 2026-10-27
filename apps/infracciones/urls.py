from django.urls import path

from apps.infracciones.views import AnulacionView, CierreView, DetalleDeInfraccionView, InfraccionesView

urlpatterns = [
    path("", InfraccionesView.as_view(), name="infracciones"),
    path("<uuid:registro_id>/", DetalleDeInfraccionView.as_view(), name="infraccion-detalle"),
    path("<uuid:registro_id>/cierre/", CierreView.as_view(), name="infraccion-cierre"),
    path("<uuid:registro_id>/anulacion/", AnulacionView.as_view(), name="infraccion-anulacion"),
]
