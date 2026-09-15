"""Endpoints de apoyo que solo existen en las pruebas (config/urls_pruebas.py).

Son lo mínimo para correr la prueba del intruso. En el producto, la vista llama a un servicio.
"""
from django.shortcuts import get_object_or_404
from rest_framework.response import Response

from apps.comun.aislamiento.vistas import VistaDeConjunto
from tests.aislamiento.models import Area


class ListaDeAreasView(VistaDeConjunto):
    def get(self, request):
        return Response([{"id": area.id, "nombre": area.nombre} for area in Area.objects.order_by("nombre")])

    def post(self, request):
        area = Area.objects.create(nombre=request.data["nombre"])
        return Response({"id": area.id, "nombre": area.nombre}, status=201)


class DetalleDeAreaView(VistaDeConjunto):
    def get(self, request, pk):
        area = get_object_or_404(Area.objects, pk=pk)
        return Response({"id": area.id, "nombre": area.nombre})
