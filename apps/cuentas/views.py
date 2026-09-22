from django.core.exceptions import ValidationError as ErrorDeValidacionDeDjango
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.comun.aislamiento.vistas import VistaDeConjunto
from apps.conjuntos.serializers import ConjuntoListaSerializer
from apps.cuentas import dos_factores, servicios
from apps.cuentas.serializers import (
    CodigoSerializer,
    CrearUsuarioSerializer,
    ElegirConjuntoSerializer,
    IniciarSesionSerializer,
    RestablecerContrasenaSerializer,
    SolicitarRecuperacionSerializer,
    UsuarioResumenSerializer,
    estado_de_la_sesion,
)
from apps.permisos.servicios import conjuntos_disponibles
from apps.permisos.views import exigir_permiso

MENSAJE_CREDENCIALES_INVALIDAS = "Correo o contraseña incorrectos."
MENSAJE_RECUPERACION_ENVIADA = (
    "Si el correo está registrado, te enviamos un enlace para restablecer la contraseña."
)
MENSAJE_ENLACE_INVALIDO = "El enlace no es válido o ya venció. Pide uno nuevo."
MENSAJE_CODIGO_INVALIDO = "Código incorrecto o vencido."


class IniciarSesionView(APIView):
    # Sin autenticación: aquí es donde nace el token.
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        datos = IniciarSesionSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        try:
            token, sesion = servicios.iniciar_sesion(**datos.validated_data)
        except servicios.CredencialesInvalidas:
            return Response(
                {"detail": MENSAJE_CREDENCIALES_INVALIDAS},
                status=status.HTTP_401_UNAUTHORIZED,
                headers={"WWW-Authenticate": "Token"},
            )
        return Response({"token": token, "vence_en": sesion.vence_en, **estado_de_la_sesion(sesion)})


class CerrarSesionView(APIView):
    permitida_sin_segundo_factor = True

    def post(self, request):
        servicios.cerrar_sesion(request.auth)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ConjuntosDisponiblesView(APIView):
    def get(self, request):
        conjuntos = conjuntos_disponibles(request.user.persona)
        return Response(ConjuntoListaSerializer(conjuntos, many=True).data)


class ConjuntoActivoView(APIView):
    """El único punto de la API que recibe un conjunto: es donde se elige (HU-26)."""

    def post(self, request):
        datos = ElegirConjuntoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        try:
            sesion = servicios.elegir_conjunto(request.auth, datos.validated_data["conjunto"])
        except servicios.ConjuntoNoDisponible:
            raise NotFound()
        return Response(estado_de_la_sesion(sesion))


# Usuarios del conjunto activo


class UsuariosView(VistaDeConjunto):
    def get(self, request):
        exigir_permiso(request, "usuario.gestionar")
        usuarios = servicios.usuarios_del_conjunto(request.auth.conjunto_activo_id)
        return Response(UsuarioResumenSerializer(usuarios, many=True).data)

    def post(self, request):
        exigir_permiso(request, "usuario.gestionar")
        datos = CrearUsuarioSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        try:
            usuario = servicios.registrar_usuario(request.auth.conjunto_activo_id, **datos.validated_data)
        except servicios.PersonaYaExiste:
            return Response(
                {"numero_documento": ["Ya existe una persona con este documento."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"id": str(usuario.id), "correo": usuario.correo}, status=status.HTTP_201_CREATED)


class DetalleDeUsuarioView(VistaDeConjunto):
    def get(self, request, usuario_id):
        exigir_permiso(request, "usuario.gestionar")
        usuario = servicios.usuarios_del_conjunto(request.auth.conjunto_activo_id).filter(pk=usuario_id).first()
        if usuario is None:
            # Sin más detalle: un 404 no confirma si la cuenta existe en otro conjunto (maestro §5.4).
            raise NotFound()
        return Response(UsuarioResumenSerializer(usuario).data)


# Recuperación de contraseña (HU-01)


class SolicitarRecuperacionView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        datos = SolicitarRecuperacionSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        servicios.solicitar_recuperacion(datos.validated_data["correo"])
        # La misma respuesta exista o no la cuenta: no revela qué correos están registrados.
        return Response({"detail": MENSAJE_RECUPERACION_ENVIADA}, status=status.HTTP_202_ACCEPTED)


class RestablecerContrasenaView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        datos = RestablecerContrasenaSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        try:
            servicios.restablecer_contrasena(**datos.validated_data)
        except servicios.EnlaceInvalido:
            return Response({"detail": MENSAJE_ENLACE_INVALIDO}, status=status.HTTP_400_BAD_REQUEST)
        except ErrorDeValidacionDeDjango as error:
            return Response({"contrasena": error.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)


# Segundo factor (HU-02). Son justo las vistas que se usan antes de tenerlo verificado.


class ConfigurarDosFactoresView(APIView):
    permitida_sin_segundo_factor = True

    def post(self, request):
        try:
            return Response(dos_factores.iniciar_configuracion(request.auth))
        except dos_factores.YaConfigurado:
            return Response(
                {"detail": "El segundo factor ya está configurado."}, status=status.HTTP_409_CONFLICT
            )


class ActivarDosFactoresView(APIView):
    permitida_sin_segundo_factor = True

    def post(self, request):
        datos = CodigoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        try:
            codigos = dos_factores.confirmar_configuracion(request.auth, datos.validated_data["codigo"])
        except dos_factores.YaConfigurado:
            return Response(
                {"detail": "El segundo factor ya está configurado."}, status=status.HTTP_409_CONFLICT
            )
        except dos_factores.SinConfigurar:
            return Response(
                {"detail": "Primero genera el código QR."}, status=status.HTTP_400_BAD_REQUEST
            )
        except dos_factores.CodigoInvalido:
            return Response({"codigo": [MENSAJE_CODIGO_INVALIDO]}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"codigos_de_respaldo": codigos, **estado_de_la_sesion(request.auth)})


class VerificarDosFactoresView(APIView):
    permitida_sin_segundo_factor = True

    def post(self, request):
        datos = CodigoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        try:
            dos_factores.verificar(request.auth, datos.validated_data["codigo"])
        except dos_factores.SinConfigurar:
            return Response(
                {"detail": "Todavía no tienes un segundo factor configurado."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except dos_factores.CodigoInvalido:
            return Response({"codigo": [MENSAJE_CODIGO_INVALIDO]}, status=status.HTTP_400_BAD_REQUEST)
        return Response(estado_de_la_sesion(request.auth))
