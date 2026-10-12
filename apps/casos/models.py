from django.db import models

from apps.comun.modelos_base.modelos import ModeloDeConjunto


class PrioridadCaso(models.TextChoices):
    BAJA = "BAJA", "Baja"
    NORMAL = "NORMAL", "Normal"
    ALTA = "ALTA", "Alta"
    URGENTE = "URGENTE", "Urgente"


class EstadoCaso(models.TextChoices):
    ABIERTO = "ABIERTO", "Abierto"
    APROBADO = "APROBADO", "Aprobado"
    RECHAZADO = "RECHAZADO", "Rechazado"
    REDIRIGIDO = "REDIRIGIDO", "Redirigido a Administración"


class Caso(ModeloDeConjunto):
    titulo = models.CharField(max_length=120)
    cuerpo = models.TextField()
    estado = models.CharField(max_length=20, choices=EstadoCaso.choices, default=EstadoCaso.ABIERTO)
    prioridad = models.CharField(max_length=10, choices=PrioridadCaso.choices, default=PrioridadCaso.NORMAL)
    motivo_rechazo = models.TextField(blank=True)
    autor = models.ForeignKey("personas.Persona", on_delete=models.PROTECT, related_name="casos")
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta(ModeloDeConjunto.Meta):
        indexes = [models.Index(fields=["conjunto", "-creado_en"], name="caso_bandeja")]

    def __str__(self):
        return self.titulo


class FotoDeCaso(ModeloDeConjunto):
    caso = models.OneToOneField(Caso, on_delete=models.PROTECT, related_name="foto")
    contenido = models.BinaryField()
    tipo = models.CharField(max_length=20)
