from django.urls import path, re_path

from apps.conjuntos.views import (
    ActivarConjuntoView,
    ConjuntoActualView,
    CrearConjuntoView,
    IdentidadDelConjuntoView,
    ImagenDelLogoView,
    LogoDelConjuntoView,
)

urlpatterns = [
    path("", CrearConjuntoView.as_view(), name="conjunto-crear"),
    path("actual/", ConjuntoActualView.as_view(), name="conjunto-actual"),
    path("actual/activar/", ActivarConjuntoView.as_view(), name="conjunto-activar"),
    path("actual/identidad/", IdentidadDelConjuntoView.as_view(), name="conjunto-identidad"),
    path("actual/identidad/logo/", LogoDelConjuntoView.as_view(), name="conjunto-logo"),
    re_path(r"^logos/(?P<huella>[0-9a-f]{64})/$", ImagenDelLogoView.as_view(), name="conjunto-logo-imagen"),
]
