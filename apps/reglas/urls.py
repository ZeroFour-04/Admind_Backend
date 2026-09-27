from django.urls import path

from apps.reglas.views import DetalleDeReglaView, ReglasView, RetirarReglaView

urlpatterns = [
    path("", ReglasView.as_view(), name="reglas"),
    path("<uuid:regla_id>/", DetalleDeReglaView.as_view(), name="regla-detalle"),
    path("<uuid:regla_id>/retirar/", RetirarReglaView.as_view(), name="regla-retirar"),
]
