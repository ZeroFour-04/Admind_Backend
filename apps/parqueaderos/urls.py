from django.urls import path

from apps.parqueaderos.views import (
    AsignacionView,
    DesactivarParqueaderoView,
    HistorialDeAsignacionesView,
    LiberacionView,
    MisParqueaderosView,
    ParqueaderosView,
)

urlpatterns = [
    path("", ParqueaderosView.as_view(), name="parqueaderos"),
    path("mios/", MisParqueaderosView.as_view(), name="parqueaderos-mios"),
    path("<uuid:parqueadero_id>/desactivar/", DesactivarParqueaderoView.as_view(), name="parqueadero-desactivar"),
    path("<uuid:parqueadero_id>/asignacion/", AsignacionView.as_view(), name="parqueadero-asignacion"),
    path("<uuid:parqueadero_id>/liberacion/", LiberacionView.as_view(), name="parqueadero-liberacion"),
    path("<uuid:parqueadero_id>/asignaciones/", HistorialDeAsignacionesView.as_view(), name="parqueadero-asignaciones"),
]
