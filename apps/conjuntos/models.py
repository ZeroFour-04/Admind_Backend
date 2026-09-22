import uuid

from django.db import models
from django.db.models import Q


class Acento(models.TextChoices):
    """Catálogo cerrado de acentos (maestro §6.3). Se guarda el slug, nunca un color."""

    VERDE = "verde", "Verde"
    AZUL = "azul", "Azul"
    INDIGO = "indigo", "Índigo"
    PURPURA = "purpura", "Púrpura"
    VINO = "vino", "Vino"
    TERRACOTA = "terracota", "Terracota"
    OCRE = "ocre", "Ocre"
    PIZARRA = "pizarra", "Pizarra"


class Conjunto(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nombre = models.CharField(max_length=80)
    direccion = models.CharField(max_length=200, blank=True)
    # El color cambia al cambiar de conjunto: dice dónde se está operando (HU-26).
    acento = models.CharField(max_length=12, choices=Acento.choices, default=Acento.VERDE)
    activo = models.BooleanField(default=True)
    operativo = models.BooleanField(default=False)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(acento__in=Acento.values),
                name="conjunto_acento_valido",
            ),
        ]

    def __str__(self):
        return self.nombre
