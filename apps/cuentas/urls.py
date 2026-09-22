from django.urls import path

from apps.cuentas.views import (
    ActivarDosFactoresView,
    CerrarSesionView,
    ConfigurarDosFactoresView,
    ConjuntoActivoView,
    ConjuntosDisponiblesView,
    DetalleDeUsuarioView,
    IniciarSesionView,
    RestablecerContrasenaView,
    SolicitarRecuperacionView,
    UsuariosView,
    VerificarDosFactoresView,
)

urlpatterns = [
    path("login/", IniciarSesionView.as_view(), name="iniciar-sesion"),
    path("logout/", CerrarSesionView.as_view(), name="cerrar-sesion"),
    path("conjuntos/", ConjuntosDisponiblesView.as_view(), name="conjuntos-disponibles"),
    path("conjunto-activo/", ConjuntoActivoView.as_view(), name="conjunto-activo"),
    path("usuarios/", UsuariosView.as_view(), name="usuarios"),
    path("usuarios/<uuid:usuario_id>/", DetalleDeUsuarioView.as_view(), name="usuario-detalle"),
    path("recuperar/", SolicitarRecuperacionView.as_view(), name="recuperar-contrasena"),
    path("recuperar/confirmar/", RestablecerContrasenaView.as_view(), name="restablecer-contrasena"),
    path("dos-factores/configurar/", ConfigurarDosFactoresView.as_view(), name="dos-factores-configurar"),
    path("dos-factores/activar/", ActivarDosFactoresView.as_view(), name="dos-factores-activar"),
    path("dos-factores/verificar/", VerificarDosFactoresView.as_view(), name="dos-factores-verificar"),
]
