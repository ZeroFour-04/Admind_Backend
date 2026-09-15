from django.urls import path

from apps.cuentas.views import CerrarSesionView, IniciarSesionView

urlpatterns = [
    path("login/", IniciarSesionView.as_view(), name="iniciar-sesion"),
    path("logout/", CerrarSesionView.as_view(), name="cerrar-sesion"),
]
