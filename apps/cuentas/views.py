from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cuentas import servicios
from apps.cuentas.serializers import (
    ConjuntoResumenSerializer,
    ElegirConjuntoSerializer,
    IniciarSesionSerializer,
)
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
        conjuntos = conjuntos_disponibles(request.user.persona)
        return Response(ConjuntoResumenSerializer(conjuntos, many=True).data)


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
