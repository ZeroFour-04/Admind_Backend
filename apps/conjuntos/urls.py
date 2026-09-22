from django.urls import path

from apps.conjuntos.views import ActivarConjuntoView, ConjuntoActualView, CrearConjuntoView

urlpatterns = [
    path("", CrearConjuntoView.as_view(), name="conjunto-crear"),
    path("actual/", ConjuntoActualView.as_view(), name="conjunto-actual"),
    path("actual/activar/", ActivarConjuntoView.as_view(), name="conjunto-activar"),
]
