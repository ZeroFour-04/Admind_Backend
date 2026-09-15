from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cuentas import servicios
from apps.cuentas.serializers import IniciarSesionSerializer

MENSAJE_CREDENCIALES_INVALIDAS = "Correo o contraseña incorrectos."


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
        return Response({"token": token, "vence_en": sesion.vence_en})


class CerrarSesionView(APIView):
    def post(self, request):
        servicios.cerrar_sesion(request.auth)
        return Response(status=status.HTTP_204_NO_CONTENT)
