"""Áreas comunes del conjunto activo (HU-09). Cada vista valida, exige su permiso y llama al servicio."""
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from apps.areas import servicios
from apps.areas.serializers import AreaSerializer, CrearAreaSerializer, EditarAreaSerializer
from apps.comun.aislamiento.vistas import VistaDeConjunto
from apps.permisos.views import exigir_permiso

MENSAJE_NOMBRE_REPETIDO = {"nombre": ["Ya existe un área con este nombre en el conjunto."]}


def area_visible(request, area_id):
    """Un área de otro conjunto, o inactiva para quien no gestiona, responde 404."""
    area = servicios.areas_visibles(request.user.persona, request.auth.conjunto_activo_id).filter(pk=area_id).first()
    if area is None:
        raise NotFound()
    return area


class AreasView(VistaDeConjunto):
    def get(self, request):
        exigir_permiso(request, "area.ver", "area.gestionar")
        areas = servicios.areas_visibles(request.user.persona, request.auth.conjunto_activo_id)
        return Response(AreaSerializer(areas, many=True).data)

    def post(self, request):
        exigir_permiso(request, "area.gestionar")
        datos = CrearAreaSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        try:
            area = servicios.crear(request.user.persona, **datos.validated_data)
        except servicios.NombreRepetido:
            return Response(MENSAJE_NOMBRE_REPETIDO, status=status.HTTP_400_BAD_REQUEST)
        return Response(AreaSerializer(area).data, status=status.HTTP_201_CREATED)


class DetalleDeAreaView(VistaDeConjunto):
    def get(self, request, area_id):
        exigir_permiso(request, "area.ver", "area.gestionar")
        return Response(AreaSerializer(area_visible(request, area_id)).data)

    def patch(self, request, area_id):
        exigir_permiso(request, "area.gestionar")
        area = area_visible(request, area_id)
        datos = EditarAreaSerializer(data=request.data, context={"area": area})
        datos.is_valid(raise_exception=True)
        campos = dict(datos.validated_data)
        en_mantenimiento = campos.pop("en_mantenimiento", None)
        modo_uso = campos.pop("modo_uso", area.modo_uso)
        cambio_de_modo = None
        try:
            if modo_uso != area.modo_uso:
                cambio_de_modo = servicios.cambiar_modo(request.user.persona, area, modo_uso, **campos)
            else:
                servicios.editar(request.user.persona, area, **campos)
        except servicios.NombreRepetido:
            return Response(MENSAJE_NOMBRE_REPETIDO, status=status.HTTP_400_BAD_REQUEST)
        if en_mantenimiento is not None:
            servicios.poner_en_mantenimiento(request.user.persona, area, en_mantenimiento)
        # Lleva datos solo si el modo cambió: lo que quedó del modo anterior, para avisarlo.
        return Response({**AreaSerializer(area).data, "cambio_de_modo": cambio_de_modo})


class DesactivarAreaView(VistaDeConjunto):
    def post(self, request, area_id):
        exigir_permiso(request, "area.gestionar")
        area = area_visible(request, area_id)
        try:
            servicios.desactivar(request.user.persona, area)
        except servicios.AreaYaInactiva:
            return Response({"detail": "El área ya está inactiva."}, status=status.HTTP_409_CONFLICT)
        return Response(AreaSerializer(area).data)
