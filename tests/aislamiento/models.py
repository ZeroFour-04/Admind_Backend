"""Tablas de apoyo que solo existen en la base de pruebas (config/settings_pruebas.py).

Imitan el caso de HU-05: una reserva que apunta a un área. No son las áreas ni las reservas del producto.
"""
from django.db import models

from apps.comun.modelos_base.modelos import ModeloDeConjunto


class Area(ModeloDeConjunto):
    nombre = models.CharField(max_length=80)


class Reserva(ModeloDeConjunto):
    area = models.ForeignKey(Area, on_delete=models.PROTECT)
