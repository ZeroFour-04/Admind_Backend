from django.urls import path

from apps.personas.views import BuscarPersonaView, VincularPersonaView

urlpatterns = [
    path("buscar/", BuscarPersonaView.as_view(), name="persona-buscar"),
    path("vincular/", VincularPersonaView.as_view(), name="persona-vincular"),
]
