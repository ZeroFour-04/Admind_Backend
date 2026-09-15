from django.urls import path

from tests.aislamiento.vistas import DetalleDeAreaView, ListaDeAreasView

urlpatterns = [
    path("areas/", ListaDeAreasView.as_view(), name="pruebas-areas"),
    path("areas/<uuid:pk>/", DetalleDeAreaView.as_view(), name="pruebas-area-detalle"),
]
