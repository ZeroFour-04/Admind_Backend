"""Reglas de reserva del conjunto activo, por niveles (HU-10). Cada vista valida, exige su permiso y llama al servicio."""
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from apps.comun.aislamiento.vistas import VistaDeConjunto
from apps.permisos.views import exigir_permiso
from apps.reglas import catalogo, servicios
from apps.reglas.catalogo import ParametrosInvalidos
from apps.reglas.models import Regla
from apps.reglas.serializers import CrearReglaSerializer, EditarReglaSerializer, ReglaSerializer

MENSAJE_REGLA_CERRADA = {"detail": "Esta regla ya no está vigente."}
MENSAJE_YA_DEFINIDA = {"detail": "Esta regla ya está definida. Cámbiala o retírala."}


def regla_del_conjunto(regla_id):
    """Una regla de otro conjunto no aparece por el manager: 404 sin detalle."""
    regla = Regla.objects.select_related("area", "creada_por").filter(pk=regla_id).first()
    if regla is None:
        raise NotFound()
    return regla


class ReglasView(VistaDeConjunto):
    def get(self, request):
        exigir_permiso(request, "regla.ver", "regla.configurar")
        return Response(ReglaSerializer(servicios.reglas_actuales(), many=True).data)

    def post(self, request):
        exigir_permiso(request, "regla.configurar")
        datos = CrearReglaSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        campos = datos.validated_data
        try:
            regla = servicios.crear(
                request.user.persona, campos["tipo"], campos["parametros"], campos["vigencia_desde"], campos["area"]
            )
        except servicios.AreaNoEncontrada:
            return Response({"area": ["Esa área no existe en este conjunto."]}, status=status.HTTP_400_BAD_REQUEST)
        except servicios.NivelEquivocado as error:
            return Response({"area": [error.mensaje]}, status=status.HTTP_400_BAD_REQUEST)
        except servicios.ReglaYaDefinida:
            return Response(MENSAJE_YA_DEFINIDA, status=status.HTTP_409_CONFLICT)
        except ParametrosInvalidos as error:
            return Response(error.errores, status=status.HTTP_400_BAD_REQUEST)
        return Response(ReglaSerializer(regla).data, status=status.HTTP_201_CREATED)


class CatalogoDeReglasView(VistaDeConjunto):
    """Los tipos que se pueden definir hoy, con su nivel, su nombre y su descripción fija (P11)."""

    def get(self, request):
        exigir_permiso(request, "regla.ver", "regla.configurar")
        return Response(catalogo.tipos_vigentes())


class DetalleDeReglaView(VistaDeConjunto):
    def get(self, request, regla_id):
        exigir_permiso(request, "regla.ver", "regla.configurar")
        return Response(ReglaSerializer(regla_del_conjunto(regla_id)).data)

    def patch(self, request, regla_id):
        """Editar crea una versión nueva; responde la nueva."""
        exigir_permiso(request, "regla.configurar")
        regla = regla_del_conjunto(regla_id)
        datos = EditarReglaSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        try:
            nueva = servicios.editar(request.user.persona, regla, datos.validated_data["parametros"])
        except servicios.ReglaCerrada:
            return Response(MENSAJE_REGLA_CERRADA, status=status.HTTP_409_CONFLICT)
        except ParametrosInvalidos as error:
            return Response(error.errores, status=status.HTTP_400_BAD_REQUEST)
        return Response(ReglaSerializer(nueva).data)


class RetirarReglaView(VistaDeConjunto):
    def post(self, request, regla_id):
        exigir_permiso(request, "regla.configurar")
        regla = regla_del_conjunto(regla_id)
        try:
            servicios.retirar(request.user.persona, regla)
        except servicios.ReglaCerrada:
            return Response(MENSAJE_REGLA_CERRADA, status=status.HTTP_409_CONFLICT)
        return Response(ReglaSerializer(regla).data)
