from django.urls import path

from apps.visitantes.views import SalidaDeVisitanteView, VisitantesView

urlpatterns = [
    path("", VisitantesView.as_view(), name="visitantes"),
    path("<uuid:visitante_id>/salida/", SalidaDeVisitanteView.as_view(), name="visitante-salida"),
]
