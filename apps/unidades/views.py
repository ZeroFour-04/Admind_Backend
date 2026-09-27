"""Unidades y vínculos del conjunto activo (HU-08). Cada vista valida, exige su permiso y llama al servicio."""
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from apps.comun.aislamiento.vistas import VistaDeConjunto
from apps.permisos.views import exigir_permiso
from apps.unidades import servicios
from apps.unidades.models import Unidad
from apps.unidades.serializers import (
    CerrarVinculoSerializer,
    CrearUnidadSerializer,
    DetalleDeUnidadSerializer,
    RegistrarVinculoSerializer,
    UnidadSerializer,
    VinculoSerializer,
)


def unidad_del_conjunto(unidad_id):
    """Una unidad de otro conjunto no aparece por el manager: 404 sin detalle."""
    unidad = Unidad.objects.filter(pk=unidad_id).first()
    if unidad is None:
        raise NotFound()
    return unidad


def detalle(unidad):
    return DetalleDeUnidadSerializer({"id": unidad.id, "nombre": unidad.nombre, **servicios.detalle_de_unidad(unidad)}).data


class UnidadesView(VistaDeConjunto):
    """Las unidades del conjunto activo. También las usa el anuncio dirigido a una vivienda (HU-25)."""

    def get(self, request):
        exigir_permiso(request, "vinculo.gestionar", "anuncio.dirigir")
        return Response(UnidadSerializer(servicios.unidades_del_conjunto(), many=True).data)

    def post(self, request):
        exigir_permiso(request, "vinculo.gestionar")
        datos = CrearUnidadSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        try:
            unidad = servicios.crear_unidad(request.user.persona, datos.validated_data["nombre"])
        except servicios.NombreRepetido:
            return Response(
                {"nombre": ["Ya existe una unidad con este nombre en el conjunto."]}, status=status.HTTP_400_BAD_REQUEST
            )
        return Response(UnidadSerializer(unidad).data, status=status.HTTP_201_CREATED)


class DetalleDeUnidadView(VistaDeConjunto):
    def get(self, request, unidad_id):
        exigir_permiso(request, "vinculo.gestionar")
        return Response(detalle(unidad_del_conjunto(unidad_id)))


class VinculosDeUnidadView(VistaDeConjunto):
    def post(self, request, unidad_id):
        exigir_permiso(request, "vinculo.gestionar")
        unidad = unidad_del_conjunto(unidad_id)
        datos = RegistrarVinculoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        campos = datos.validated_data
        try:
            vinculo = servicios.registrar_vinculo(
                request.user.persona,
                unidad,
                campos["persona"],
                campos["tipo"],
                campos["reside"],
                campos.get("vigencia_desde"),
            )
        except servicios.PersonaSinAsignacion:
            return Response(
                {"persona": ["Primero vincula a la persona al conjunto."]}, status=status.HTTP_400_BAD_REQUEST
            )
        except servicios.VinculoDuplicado:
            return Response(
                {"detail": "Esta persona ya tiene un vínculo vigente de ese tipo con la unidad."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(VinculoSerializer(vinculo).data, status=status.HTTP_201_CREATED)


class CerrarVinculoView(VistaDeConjunto):
    def post(self, request, unidad_id, vinculo_id):
        exigir_permiso(request, "vinculo.gestionar")
        unidad = unidad_del_conjunto(unidad_id)
        vinculo = unidad.vinculos.filter(pk=vinculo_id).select_related("persona").first()
        if vinculo is None:
            raise NotFound()
        datos = CerrarVinculoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        try:
            servicios.cerrar_vinculo(request.user.persona, vinculo, datos.validated_data.get("vigencia_hasta"))
        except servicios.VinculoYaCerrado:
            return Response({"detail": "Este vínculo ya está cerrado."}, status=status.HTTP_409_CONFLICT)
        except servicios.CierreAntesDelInicio:
            return Response(
                {"vigencia_hasta": ["El cierre no puede ser anterior al inicio del vínculo."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(detalle(unidad))
