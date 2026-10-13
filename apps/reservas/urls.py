from django.urls import path

from apps.reservas.views import (
    BandejaDeSolicitudesView,
    ComprobanteDeSolicitudView,
    ComprobantesDeSolicitudView,
    DecidirSolicitudView,
    DescartarSolicitudView,
    DetalleDeSolicitudView,
    EnviarSolicitudView,
    FranjasView,
    LiberarSolicitudView,
    MarcarDisponibilidadView,
    PagoDeSolicitudView,
    RetirarPagoDeSolicitudView,
    SolicitudesDeAreaView,
    SolicitudesView,
)

urlpatterns = [
    path("franjas/", FranjasView.as_view(), name="franjas"),
    path("bandeja/", BandejaDeSolicitudesView.as_view(), name="solicitudes-bandeja"),
    path("areas/<uuid:area_id>/solicitudes/", SolicitudesDeAreaView.as_view(), name="solicitudes-area"),
    path("solicitudes/", SolicitudesView.as_view(), name="solicitudes"),
    path("campanas/", MarcarDisponibilidadView.as_view(), name="campanas"),
    path("solicitudes/<uuid:solicitud_id>/decision/", DecidirSolicitudView.as_view(), name="solicitud-decision"),
    path("solicitudes/<uuid:solicitud_id>/descarte/", DescartarSolicitudView.as_view(), name="solicitud-descarte"),
    path("solicitudes/<uuid:solicitud_id>/", DetalleDeSolicitudView.as_view(), name="solicitud-detalle"),
    path("solicitudes/<uuid:solicitud_id>/liberar/", LiberarSolicitudView.as_view(), name="solicitud-liberar"),
    path("solicitudes/<uuid:solicitud_id>/enviar/", EnviarSolicitudView.as_view(), name="solicitud-enviar"),
    path("solicitudes/<uuid:solicitud_id>/pago/", PagoDeSolicitudView.as_view(), name="solicitud-pago"),
    path(
        "solicitudes/<uuid:solicitud_id>/pago/retirar/",
        RetirarPagoDeSolicitudView.as_view(),
        name="solicitud-pago-retirar",
    ),
    path(
        "solicitudes/<uuid:solicitud_id>/comprobantes/",
        ComprobantesDeSolicitudView.as_view(),
        name="solicitud-comprobantes",
    ),
    path("comprobantes/<uuid:comprobante_id>/", ComprobanteDeSolicitudView.as_view(), name="solicitud-comprobante"),
]
