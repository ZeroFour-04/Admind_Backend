from django.urls import path

from apps.parqueaderos.views import DesactivarParqueaderoView, ParqueaderosView

urlpatterns = [
    path("", ParqueaderosView.as_view(), name="parqueaderos"),
    path("<uuid:parqueadero_id>/desactivar/", DesactivarParqueaderoView.as_view(), name="parqueadero-desactivar"),
]
