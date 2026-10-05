from django.db import models
from django.db.models import Q

from apps.comun.modelos_base.modelos import ModeloDeConjunto

# Cuántas fotos lleva un anuncio como máximo. La base lo hace cumplir (ver FotoDeAnuncio).
MAXIMO_DE_FOTOS = 4


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


class FotoDeAnuncio(ModeloDeConjunto):
    """Una foto del anuncio (HU-25). Va en su propia tabla para que leer un Anuncio no traiga la imagen.

    Se suben al publicar y no cambian después. Cada foto ocupa un `orden` distinto, de 0 a
    MAXIMO_DE_FOTOS - 1: con eso la base no deja guardar una foto de más.
    """

    # La FK compuesta impide que apunte a un anuncio de otro conjunto.
    anuncio = models.ForeignKey(Anuncio, on_delete=models.PROTECT, related_name="fotos")
    contenido = models.BinaryField()
    # El tipo real, leído de la firma del archivo; nunca el que declara quien la sube.
    tipo = models.CharField(max_length=20)
    orden = models.PositiveSmallIntegerField()

    class Meta(ModeloDeConjunto.Meta):
        ordering = ["orden"]
        constraints = [
            *ModeloDeConjunto.Meta.constraints,
            models.UniqueConstraint(fields=["anuncio", "orden"], name="foto_orden_unico_por_anuncio"),
            models.CheckConstraint(condition=Q(orden__lt=MAXIMO_DE_FOTOS), name="foto_orden_dentro_del_tope"),
        ]
        indexes = [models.Index(fields=["conjunto", "anuncio", "orden"], name="foto_de_anuncio")]
