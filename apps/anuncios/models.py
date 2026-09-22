from django.db import models
from django.db.models import Q

from apps.comun.modelos_base.modelos import ModeloDeConjunto


class Alcance(models.TextChoices):
    """Los dos alcances de un anuncio (maestro §5.7). Ninguno es una lista de personas."""

    CONJUNTO = "conjunto", "Todo el conjunto"
    VIVIENDA = "vivienda", "Una vivienda"


class Anuncio(ModeloDeConjunto):
    titulo = models.CharField(max_length=120)
    cuerpo = models.TextField()
    alcance = models.CharField(max_length=10, choices=Alcance.choices)
    # Solo con alcance vivienda. La FK compuesta impide que apunte a una unidad de otro conjunto.
    unidad = models.ForeignKey(
        "unidades.Unidad", on_delete=models.PROTECT, null=True, blank=True, related_name="anuncios"
    )
    autor = models.ForeignKey("personas.Persona", on_delete=models.PROTECT, related_name="anuncios")
    publicado_en = models.DateTimeField(auto_now_add=True)
    editado_en = models.DateTimeField(null=True, blank=True)

    class Meta(ModeloDeConjunto.Meta):
        constraints = [
            *ModeloDeConjunto.Meta.constraints,
            models.CheckConstraint(
                condition=(
                    Q(alcance=Alcance.CONJUNTO, unidad__isnull=True)
                    | Q(alcance=Alcance.VIVIENDA, unidad__isnull=False)
                ),
                name="anuncio_unidad_segun_alcance",
            ),
        ]
        indexes = [models.Index(fields=["conjunto", "-publicado_en"], name="anuncio_tablon")]

    def __str__(self):
        return self.titulo
