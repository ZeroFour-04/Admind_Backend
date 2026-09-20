from django.db import transaction
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cuentas import servicios
from apps.cuentas.serializers import (
    ConjuntoResumenSerializer,
    ConjuntoListaSerializer,
    CrearConjuntoSerializer,
    CrearUsuarioSerializer,
    ElegirConjuntoSerializer,
    IniciarSesionSerializer,
    UsuarioResumenSerializer,
)
from apps.cuentas.models import Usuario
from apps.personas.models import Persona
from apps.conjuntos.models import Conjunto
from apps.permisos.models import Asignacion
from apps.permisos.servicios import conjuntos_disponibles, permisos_efectivos

MENSAJE_CREDENCIALES_INVALIDAS = "Correo o contraseña incorrectos."


def estado_de_la_sesion(sesion):
    conjunto = sesion.conjunto_activo
    return {
        "conjunto_activo": ConjuntoResumenSerializer(conjunto).data if conjunto else None,
        "permisos": sorted(permisos_efectivos(sesion.usuario.persona, sesion.conjunto_activo_id)),
    }


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
    def post(self, request):
        servicios.cerrar_sesion(request.auth)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ConjuntosDisponiblesView(APIView):
    def get(self, request):
        permisos = permisos_efectivos(request.user.persona, request.auth.conjunto_activo_id)
        if "conjunto.crear" in permisos:
            conjuntos = Conjunto.objects.filter(activo=True).order_by("nombre")
        else:
            conjuntos = conjuntos_disponibles(request.user.persona)
        return Response(ConjuntoListaSerializer(conjuntos, many=True).data)

    def post(self, request):
        permisos = permisos_efectivos(request.user.persona, request.auth.conjunto_activo_id)
        if "conjunto.crear" not in permisos:
            return Response(
                {"detail": "No tienes permiso para crear conjuntos."},
                status=status.HTTP_403_FORBIDDEN,
            )
        datos = CrearConjuntoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        conjunto = Conjunto.objects.create(**datos.validated_data)
        return Response(ConjuntoListaSerializer(conjunto).data, status=status.HTTP_201_CREATED)


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


class CrearUsuarioView(APIView):
    def _puede_gestionar(self, request):
        return "usuario.gestionar" in permisos_efectivos(
            request.user.persona, request.auth.conjunto_activo_id
        )

    def get(self, request, usuario_id=None):
        if not self._puede_gestionar(request):
            return Response(
                {"detail": "No tienes permiso para gestionar usuarios."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if usuario_id:
            try:
                usuario = Usuario.objects.select_related("persona").get(id=usuario_id)
            except Usuario.DoesNotExist:
                raise NotFound()
            return Response(UsuarioResumenSerializer(usuario).data)
        usuarios = Usuario.objects.select_related("persona").order_by("persona__apellidos", "persona__nombres")
        return Response(UsuarioResumenSerializer(usuarios, many=True).data)

    def post(self, request):
        if "usuario.gestionar" not in permisos_efectivos(
            request.user.persona, request.auth.conjunto_activo_id
        ):
            return Response(
                {"detail": "No tienes permiso para gestionar usuarios."},
                status=status.HTTP_403_FORBIDDEN,
            )

        datos = CrearUsuarioSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        with transaction.atomic():
            persona = Persona.objects.create(
                tipo_documento=datos.validated_data["tipo_documento"],
                numero_documento=datos.validated_data["numero_documento"],
                nombres=datos.validated_data["nombres"],
                apellidos=datos.validated_data["apellidos"],
                telefono=datos.validated_data.get("telefono", ""),
            )
            usuario = Usuario.objects.create_user(
                correo=datos.validated_data["correo"],
                password=datos.validated_data["contrasena"],
                persona=persona,
            )
            Asignacion.objects.create(
                persona=persona,
                rol=datos.validated_data["rol"],
                conjunto_id=request.auth.conjunto_activo_id,
            )
        return Response(
            {"id": str(usuario.id), "correo": usuario.correo},
            status=status.HTTP_201_CREATED,
        )
