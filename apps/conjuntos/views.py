"""Asistente de creación (HU-03) e identidad visual (HU-21) de los conjuntos.

Cada vista valida, exige su permiso y llama al servicio.
"""
from django.http import HttpResponse
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.comun.aislamiento.vistas import VistaDeConjunto
from apps.conjuntos import servicios
from apps.conjuntos.models import Conjunto
from apps.conjuntos.serializers import (
    AcentoSerializer,
    ConjuntoListaSerializer,
    ConjuntoResumenSerializer,
    DatosDeConjuntoSerializer,
    LogoSerializer,
)
from apps.cuentas import servicios as servicios_de_cuentas
from apps.cuentas.serializers import estado_de_la_sesion
from apps.permisos.servicios import es_superusuario, puede_crear_conjuntos, tiene_permiso
from apps.permisos.views import MENSAJE_SIN_PERMISO, exigir_permiso


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

    No hereda de VistaDeConjunto porque se crea desde el selector, sin conjunto activo. El permiso
    `conjunto.crear` se mira en todos los conjuntos de la persona (Superusuario o Administración),
    no solo en el activo: quien administra uno puede crear otro apenas inicia sesión.
    """

    def post(self, request):
        if not puede_crear_conjuntos(request.user.persona):
            raise PermissionDenied(MENSAJE_SIN_PERMISO)
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
        if "acento" in request.data or "color" in request.data:
            exigir_permiso(request, "conjunto.branding", "conjunto.activar")
        conjunto = Conjunto.objects.get(pk=request.auth.conjunto_activo_id)
        datos = DatosDeConjuntoSerializer(conjunto, data=request.data, partial=True)
        datos.is_valid(raise_exception=True)
        servicios.editar_datos(conjunto, **datos.validated_data)
        return Response(resumen_del_asistente(request, conjunto))

    def delete(self, request):
        if not es_superusuario(request.user.persona):
            raise PermissionDenied(MENSAJE_SIN_PERMISO)
        conjunto = Conjunto.objects.get(pk=request.auth.conjunto_activo_id)
        try:
            servicios.eliminar(conjunto)
        except servicios.ConjuntoYaInactivo:
            return Response({"detail": "Este conjunto ya fue eliminado."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)


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


# Identidad visual (HU-21): el color, uno de los ocho del catálogo o uno propio, y la foto 1:1.

# El Superusuario también, como en el resto del asistente: configura el conjunto que está creando.
PERMISOS_DE_IDENTIDAD = ("conjunto.branding", "conjunto.activar")


class IdentidadDelConjuntoView(VistaDeConjunto):
    def get(self, request):
        exigir_permiso(request, *PERMISOS_DE_IDENTIDAD)
        conjunto = Conjunto.objects.get(pk=request.auth.conjunto_activo_id)
        return Response(ConjuntoResumenSerializer(conjunto).data)

    def patch(self, request):
        exigir_permiso(request, *PERMISOS_DE_IDENTIDAD)
        datos = AcentoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        conjunto = Conjunto.objects.get(pk=request.auth.conjunto_activo_id)
        servicios.editar_datos(conjunto, **datos.validated_data)
        return Response(ConjuntoResumenSerializer(conjunto).data)


class LogoDelConjuntoView(VistaDeConjunto):
    def put(self, request):
        exigir_permiso(request, *PERMISOS_DE_IDENTIDAD)
        datos = LogoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        # Se lee un byte más del límite: basta para saber que se pasa, sin cargar un archivo enorme.
        contenido = datos.validated_data["archivo"].read(servicios.TAMANO_MAXIMO_LOGO + 1)
        conjunto = Conjunto.objects.get(pk=request.auth.conjunto_activo_id)
        try:
            servicios.guardar_logo(conjunto, contenido)
        except servicios.LogoInvalido as error:
            return Response({"archivo": [error.mensaje]}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ConjuntoResumenSerializer(conjunto).data)

    def delete(self, request):
        exigir_permiso(request, *PERMISOS_DE_IDENTIDAD)
        conjunto = Conjunto.objects.get(pk=request.auth.conjunto_activo_id)
        servicios.quitar_logo(conjunto)
        return Response(ConjuntoResumenSerializer(conjunto).data)


class ImagenDelLogoView(APIView):
    """La imagen del logo, pedida por su huella.

    No es una VistaDeConjunto porque el selector muestra el logo de conjuntos que todavía no son
    el activo. No recibe el conjunto: con la huella basta, y solo se entrega si es de un conjunto
    donde la persona puede operar. Si no, 404, igual que si no existiera.
    """

    def get(self, request, huella):
        logo = servicios.logo_por_huella(request.user.persona, huella)
        if logo is None:
            raise NotFound()
        return HttpResponse(bytes(logo.contenido), content_type=logo.tipo)
