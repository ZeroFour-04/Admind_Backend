from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from apps.cuentas import servicios

MENSAJE_TOKEN_INVALIDO = "Token inválido o vencido."


class AutenticacionPorToken(BaseAuthentication):
    """Lee `Authorization: Token <token>` en cada petición y busca su sesión en la base."""

    palabra = b"token"

    def authenticate(self, request):
        partes = get_authorization_header(request).split()
        if not partes or partes[0].lower() != self.palabra:
            return None
        if len(partes) != 2:
            raise AuthenticationFailed(MENSAJE_TOKEN_INVALIDO)
        try:
            token = partes[1].decode()
        except UnicodeDecodeError:
            raise AuthenticationFailed(MENSAJE_TOKEN_INVALIDO)

        sesion = servicios.sesion_vigente(token)
        if sesion is None:
            raise AuthenticationFailed(MENSAJE_TOKEN_INVALIDO)
        return sesion.usuario, sesion

    def authenticate_header(self, request):
        # Con esto DRF responde 401 y no 403 cuando falta el token.
        return "Token"
