from django.urls import path

from apps.cuentas.views import (
    CerrarSesionView,
    ConjuntoActivoView,
    ConjuntosDisponiblesView,
    CrearUsuarioView,
    IniciarSesionView,
)

urlpatterns = [
    path("login/", IniciarSesionView.as_view(), name="iniciar-sesion"),
    path("logout/", CerrarSesionView.as_view(), name="cerrar-sesion"),
    path("conjuntos/", ConjuntosDisponiblesView.as_view(), name="conjuntos-disponibles"),
    path("conjunto-activo/", ConjuntoActivoView.as_view(), name="conjunto-activo"),
    path("usuarios/", CrearUsuarioView.as_view(), name="crear-usuario"),
    path("usuarios/<uuid:usuario_id>/", CrearUsuarioView.as_view(), name="detalle-usuario"),
]
