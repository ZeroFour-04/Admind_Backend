import uuid

from django.db import models
from django.db.models import Q

from apps.comun.modelos_base.modelos import ModeloDeConjunto


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
    # Huella SHA-256 del logo, vacía si no tiene (HU-21). La imagen vive en LogoDeConjunto: aquí
    # solo queda la huella, para que el selector sepa qué logo mostrar sin cargar ninguna imagen.
    logo_huella = models.CharField(max_length=64, blank=True)
    activo = models.BooleanField(default=True)
    operativo = models.BooleanField(default=False)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(acento__in=Acento.values),
                name="conjunto_acento_valido",
            ),
            models.CheckConstraint(
                condition=Q(logo_huella="") | Q(logo_huella__regex=r"^[0-9a-f]{64}$"),
                name="conjunto_logo_huella_valida",
            ),
        ]

    def __str__(self):
        return self.nombre


class LogoDeConjunto(ModeloDeConjunto):
    """La imagen del logo (HU-21). Va en su propia tabla para que cargar un Conjunto no traiga la imagen."""

    contenido = models.BinaryField()
    # El tipo real, leído de la firma del archivo; nunca el que declara quien lo sube.
    tipo = models.CharField(max_length=20)
    subido_en = models.DateTimeField(auto_now=True)

    class Meta(ModeloDeConjunto.Meta):
        constraints = [
            *ModeloDeConjunto.Meta.constraints,
            models.UniqueConstraint(fields=["conjunto"], name="logo_uno_por_conjunto"),
        ]
