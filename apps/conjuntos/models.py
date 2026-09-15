import uuid

from django.db import models


class Conjunto(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nombre = models.CharField(max_length=80)
    direccion = models.CharField(max_length=200, blank=True)
    activo = models.BooleanField(default=True)
    operativo = models.BooleanField(default=False)
    creado_en = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre
