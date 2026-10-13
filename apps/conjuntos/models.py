import uuid

from django.db import models
from django.db.models import Q

from apps.comun.modelos_base.modelos import ModeloDeConjunto


class Acento(models.TextChoices):
    """Los ocho acentos del catálogo (maestro §6.3) y el personalizado.

    Con uno del catálogo se guarda solo el slug: su paleta vive en el frontend. Con el
    personalizado se guarda además el color que eligió la Administración.
    """

    VERDE = "verde", "Verde"
    AZUL = "azul", "Azul"
    INDIGO = "indigo", "Índigo"
    PURPURA = "purpura", "Púrpura"
    VINO = "vino", "Vino"
    TERRACOTA = "terracota", "Terracota"
    OCRE = "ocre", "Ocre"
    PIZARRA = "pizarra", "Pizarra"
    PERSONALIZADO = "personalizado", "Personalizado"


class Conjunto(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nombre = models.CharField(max_length=30)
    direccion = models.CharField(max_length=200, blank=True)
    # El color cambia al cambiar de conjunto: dice dónde se está operando (HU-26).
    acento = models.CharField(max_length=16, choices=Acento.choices, default=Acento.VERDE)
    # Hex "#rrggbb" en minúsculas, solo con el acento personalizado; vacío con los del catálogo.
    color_personalizado = models.CharField(max_length=7, blank=True)
    # Huella SHA-256 del logo, vacía si no tiene (HU-21). El logo es la foto cuadrada (1:1) del
    # conjunto. La imagen vive en LogoDeConjunto: aquí solo queda la huella, para que el selector
    # sepa qué foto mostrar sin cargar ninguna imagen.
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
            # El personalizado siempre trae su color, y los del catálogo nunca traen uno.
            models.CheckConstraint(
                condition=(
                    Q(acento=Acento.PERSONALIZADO, color_personalizado__regex=r"^#[0-9a-f]{6}$")
                    | (~Q(acento=Acento.PERSONALIZADO) & Q(color_personalizado=""))
                ),
                name="conjunto_color_personalizado_valido",
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
