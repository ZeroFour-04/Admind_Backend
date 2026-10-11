from django.urls import path

from apps.pagos.views import (
    ComprobanteView,
    ConfirmacionView,
    MisPagosView,
    PagosDeAdministracionView,
    ReportesView,
)

urlpatterns = [
    path("administracion/", PagosDeAdministracionView.as_view(), name="pagos-administracion"),
    path("administracion/reportes/", ReportesView.as_view(), name="pago-reportes"),
    path("administracion/mios/", MisPagosView.as_view(), name="pagos-mios"),
    path("administracion/comprobantes/<uuid:comprobante_id>/", ComprobanteView.as_view(), name="pago-comprobante"),
    path(
        "administracion/<uuid:unidad_id>/<str:periodo>/confirmacion/",
        ConfirmacionView.as_view(),
        name="pago-confirmacion",
    ),
]
