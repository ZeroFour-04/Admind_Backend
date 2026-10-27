from django.db import models
from django.db.models import Q

from apps.comun.modelos_base.modelos import ModeloDeConjunto


class TipoDeDocumento(models.TextChoices):
    """Los documentos que guarda el conjunto. Las actas de asamblea no entran (HU-33, D2 b): serían una opción más."""

    REGLAMENTO = "reglamento", "Reglamento de propiedad horizontal"
    MANUAL = "manual", "Manual de convivencia"


class Documento(ModeloDeConjunto):
    """Un documento del conjunto en PDF: su reglamento o su manual de convivencia (HU-33).

    Subir uno nuevo del mismo tipo no borra el anterior: el vigente de cada tipo es el más reciente y los
    demás quedan como versiones archivadas. Antes se llamaba `Reglamento`; las filas de entonces son del
    tipo `reglamento`.
    """

    tipo = models.CharField(max_length=20, choices=TipoDeDocumento.choices)
    contenido = models.BinaryField()
    nombre = models.CharField(max_length=120)
    peso = models.PositiveIntegerField()  # en bytes
    huella = models.CharField(max_length=64)  # SHA-256 del contenido
    subido_por = models.ForeignKey("personas.Persona", on_delete=models.PROTECT, related_name="documentos_subidos")
    subido_en = models.DateTimeField(auto_now_add=True)

    class Meta(ModeloDeConjunto.Meta):
        constraints = [
            *ModeloDeConjunto.Meta.constraints,
            models.CheckConstraint(condition=Q(tipo__in=TipoDeDocumento.values), name="documento_tipo_valido"),
        ]
        indexes = [models.Index(fields=["conjunto", "tipo", "subido_en"], name="documento_por_tipo_y_fecha")]

    def __str__(self):
        return self.nombre
