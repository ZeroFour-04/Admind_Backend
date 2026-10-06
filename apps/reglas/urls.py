from django.urls import path

from apps.reglas.views import CatalogoDeReglasView, DetalleDeReglaView, ReglasView, RetirarReglaView

urlpatterns = [
    path("", ReglasView.as_view(), name="reglas"),
    path("catalogo/", CatalogoDeReglasView.as_view(), name="reglas-catalogo"),
    path("<uuid:regla_id>/", DetalleDeReglaView.as_view(), name="regla-detalle"),
    path("<uuid:regla_id>/retirar/", RetirarReglaView.as_view(), name="regla-retirar"),
]
