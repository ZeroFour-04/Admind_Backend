from django.urls import path

from apps.cuentas.views import (
    CerrarSesionView,
    ConjuntoActivoView,
    ConjuntosDisponiblesView,
    IniciarSesionView,
)

urlpatterns = [
    path("login/", IniciarSesionView.as_view(), name="iniciar-sesion"),
    path("logout/", CerrarSesionView.as_view(), name="cerrar-sesion"),
    path("conjuntos/", ConjuntosDisponiblesView.as_view(), name="conjuntos-disponibles"),
    path("conjunto-activo/", ConjuntoActivoView.as_view(), name="conjunto-activo"),
]
