import uuid

from django.db import models
from django.db.models import Q


class TipoDocumento(models.TextChoices):
    CC = "CC", "Cédula de ciudadanía"
    TI = "TI", "Tarjeta de identidad"
    CE = "CE", "Cédula de extranjería"
    PAS = "PAS", "Pasaporte"
    PPT = "PPT", "Permiso por Protección Temporal"


def normalizar_documento(numero):
    """Sin puntos, sin espacios y sin ceros a la izquierda (maestro §5.2)."""
    return numero.replace(".", "").replace(" ", "").upper().lstrip("0")


class Persona(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tipo_documento = models.CharField(max_length=3, choices=TipoDocumento.choices)
    numero_documento = models.CharField(max_length=20)
    nombres = models.CharField(max_length=30)
    apellidos = models.CharField(max_length=30)
    telefono = models.CharField(max_length=15, blank=True)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tipo_documento", "numero_documento"],
                name="persona_documento_unico",
            ),
            models.CheckConstraint(
                condition=Q(tipo_documento__in=TipoDocumento.values),
                name="persona_tipo_documento_valido",
            ),
            models.CheckConstraint(
                condition=Q(numero_documento__regex=r"^[A-Z1-9][A-Z0-9]*$"),
                name="persona_documento_normalizado",
            ),
            models.CheckConstraint(
                condition=Q(telefono="") | Q(telefono__regex=r"^\+?[0-9]{7,10}$"),
                name="persona_telefono_valido",
            ),
        ]

    def save(self, *args, **kwargs):
        self.numero_documento = normalizar_documento(self.numero_documento)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nombres} {self.apellidos}"