from django.urls import path

from apps.reservas.views import (
    DetalleDeSolicitudView,
    BandejaDeSolicitudesView,
    DecidirSolicitudView,
    EnviarSolicitudView,
    FranjasView,
    LiberarSolicitudView,
    SolicitudesDeAreaView,
    SolicitudesView,
)

urlpatterns = [
    path("franjas/", FranjasView.as_view(), name="franjas"),
    path("bandeja/", BandejaDeSolicitudesView.as_view(), name="solicitudes-bandeja"),
    path("areas/<uuid:area_id>/solicitudes/", SolicitudesDeAreaView.as_view(), name="solicitudes-area"),
    path("solicitudes/", SolicitudesView.as_view(), name="solicitudes"),
    path("solicitudes/<uuid:solicitud_id>/decision/", DecidirSolicitudView.as_view(), name="solicitud-decision"),
    path("solicitudes/<uuid:solicitud_id>/", DetalleDeSolicitudView.as_view(), name="solicitud-detalle"),
    path("solicitudes/<uuid:solicitud_id>/liberar/", LiberarSolicitudView.as_view(), name="solicitud-liberar"),
    path("solicitudes/<uuid:solicitud_id>/enviar/", EnviarSolicitudView.as_view(), name="solicitud-enviar"),
]
