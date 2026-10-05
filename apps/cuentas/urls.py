from django.urls import path

from apps.cuentas.views import (
    ActivarDosFactoresView,
    CambiarRolView,
    CerrarSesionView,
    ConfigurarDosFactoresView,
    ConjuntoActivoView,
    ConjuntosDisponiblesView,
    DetalleDeUsuarioView,
    RetirarRolView,
    RetirarUsuarioDelConjuntoView,
    RolesDeUsuarioView,
    IniciarSesionView,
    PerfilDeUsuarioView,
    RestablecerContrasenaView,
    RestablecerDosFactoresView,
    SolicitarRecuperacionView,
    SolicitarRestablecerDosFactoresView,
    UsuariosView,
    VerificarDosFactoresView,
)

urlpatterns = [
    path("login/", IniciarSesionView.as_view(), name="iniciar-sesion"),
    path("logout/", CerrarSesionView.as_view(), name="cerrar-sesion"),
    path("conjuntos/", ConjuntosDisponiblesView.as_view(), name="conjuntos-disponibles"),
    path("conjunto-activo/", ConjuntoActivoView.as_view(), name="conjunto-activo"),
    path("usuarios/", UsuariosView.as_view(), name="usuarios"),
    path("usuarios/perfil/", PerfilDeUsuarioView.as_view(), name="usuario-perfil"),
    path("usuarios/<uuid:usuario_id>/", DetalleDeUsuarioView.as_view(), name="usuario-detalle"),
    path("usuarios/<uuid:usuario_id>/roles/", RolesDeUsuarioView.as_view(), name="usuario-roles"),
    path("usuarios/<uuid:usuario_id>/eliminar/", RetirarUsuarioDelConjuntoView.as_view(), name="usuario-eliminar"),
    path(
        "usuarios/<uuid:usuario_id>/roles/<uuid:asignacion_id>/cambiar/",
        CambiarRolView.as_view(),
        name="usuario-rol-cambiar",
    ),
    path(
        "usuarios/<uuid:usuario_id>/roles/<uuid:asignacion_id>/retirar/",
        RetirarRolView.as_view(),
        name="usuario-rol-retirar",
    ),
    path("recuperar/", SolicitarRecuperacionView.as_view(), name="recuperar-contrasena"),
    path("recuperar/confirmar/", RestablecerContrasenaView.as_view(), name="restablecer-contrasena"),
    path("dos-factores/configurar/", ConfigurarDosFactoresView.as_view(), name="dos-factores-configurar"),
    path("dos-factores/activar/", ActivarDosFactoresView.as_view(), name="dos-factores-activar"),
    path("dos-factores/verificar/", VerificarDosFactoresView.as_view(), name="dos-factores-verificar"),
    path(
        "dos-factores/restablecer/",
        SolicitarRestablecerDosFactoresView.as_view(),
        name="dos-factores-restablecer",
    ),
    path(
        "dos-factores/restablecer/confirmar/",
        RestablecerDosFactoresView.as_view(),
        name="dos-factores-restablecer-confirmar",
    ),
]
