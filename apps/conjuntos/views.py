"""Asistente de creación de conjuntos (HU-03). Cada vista valida, exige su permiso y llama al servicio."""
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.comun.aislamiento.vistas import VistaDeConjunto
from apps.conjuntos import servicios
from apps.conjuntos.models import Conjunto
from apps.conjuntos.serializers import ConjuntoListaSerializer, DatosDeConjuntoSerializer
from apps.cuentas import servicios as servicios_de_cuentas
from apps.cuentas.serializers import estado_de_la_sesion
from apps.permisos.servicios import tiene_permiso
from apps.permisos.views import exigir_permiso


def resumen_del_asistente(request, conjunto):
    return {
        "conjunto": {**ConjuntoListaSerializer(conjunto).data, "operativo": conjunto.operativo},
        "administradores": [
            {"id": asignacion.persona.id, "nombre": str(asignacion.persona)}
            for asignacion in servicios.administradores(conjunto)
        ],
        "requisitos": [requisito.como_dict() for requisito in servicios.requisitos_para_operar(conjunto)],
        "puede_activar": tiene_permiso(request.user.persona, conjunto.id, "conjunto.activar"),
    }


class CrearConjuntoView(APIView):
    """Paso 1: datos básicos.

    No hereda de VistaDeConjunto porque el Superusuario crea conjuntos sin tener uno activo.
    Administración, en cambio, recibe `conjunto.crear` de su rol en el conjunto activo.
    """

    def post(self, request):
        exigir_permiso(request, "conjunto.crear")
        datos = DatosDeConjuntoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        conjunto = servicios.crear_conjunto(request.user.persona, **datos.validated_data)
        # El asistente sigue sobre el conjunto nuevo: pasa a ser el conjunto activo de la sesión.
        sesion = servicios_de_cuentas.elegir_conjunto(request.auth, conjunto.id)
        return Response(
            {"conjunto": ConjuntoListaSerializer(conjunto).data, **estado_de_la_sesion(sesion)},
            status=status.HTTP_201_CREATED,
        )


class ConjuntoActualView(VistaDeConjunto):
    """Resumen del asistente (paso 3) y edición de los datos básicos del conjunto activo.

    Lo usan Administración (`conjunto.editar`) y el Superusuario, que no opera dentro de los
    conjuntos pero sí configura el que está creando: por eso también basta `conjunto.activar`.
    """

    def get(self, request):
        exigir_permiso(request, "conjunto.editar", "conjunto.activar")
        conjunto = Conjunto.objects.get(pk=request.auth.conjunto_activo_id)
        return Response(resumen_del_asistente(request, conjunto))

    def patch(self, request):
        exigir_permiso(request, "conjunto.editar", "conjunto.activar")
        if "acento" in request.data:
            exigir_permiso(request, "conjunto.branding", "conjunto.activar")
        conjunto = Conjunto.objects.get(pk=request.auth.conjunto_activo_id)
        datos = DatosDeConjuntoSerializer(conjunto, data=request.data, partial=True)
        datos.is_valid(raise_exception=True)
        servicios.editar_datos(conjunto, **datos.validated_data)
        return Response(resumen_del_asistente(request, conjunto))


class ActivarConjuntoView(VistaDeConjunto):
    def post(self, request):
        exigir_permiso(request, "conjunto.activar")
        conjunto = Conjunto.objects.get(pk=request.auth.conjunto_activo_id)
        try:
            servicios.activar(conjunto)
        except servicios.ConjuntoIncompleto as error:
            return Response(
                {
                    "detail": "El conjunto todavía no puede quedar operativo.",
                    "faltantes": [requisito.descripcion for requisito in error.faltantes],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(resumen_del_asistente(request, conjunto))
