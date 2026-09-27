from django.urls import path

from apps.reservas.views import (
    DetalleDeSolicitudView,
    EnviarSolicitudView,
    FranjasView,
    LiberarSolicitudView,
    SolicitudesView,
)

urlpatterns = [
    path("franjas/", FranjasView.as_view(), name="franjas"),
    path("solicitudes/", SolicitudesView.as_view(), name="solicitudes"),
    path("solicitudes/<uuid:solicitud_id>/", DetalleDeSolicitudView.as_view(), name="solicitud-detalle"),
    path("solicitudes/<uuid:solicitud_id>/liberar/", LiberarSolicitudView.as_view(), name="solicitud-liberar"),
    path("solicitudes/<uuid:solicitud_id>/enviar/", EnviarSolicitudView.as_view(), name="solicitud-enviar"),
]
