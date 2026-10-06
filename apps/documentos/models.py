from django.db import models

from apps.comun.modelos_base.modelos import ModeloDeConjunto


class Reglamento(ModeloDeConjunto):
    """El reglamento de propiedad horizontal del conjunto, en PDF (HU-33; lo mínimo que exige HU-03).

    Subir uno nuevo no borra el anterior: el vigente es el más reciente.
    """

    contenido = models.BinaryField()
    nombre = models.CharField(max_length=120)
    peso = models.PositiveIntegerField()  # en bytes
    huella = models.CharField(max_length=64)  # SHA-256 del contenido
    subido_por = models.ForeignKey("personas.Persona", on_delete=models.PROTECT, related_name="reglamentos_subidos")
    subido_en = models.DateTimeField(auto_now_add=True)

    class Meta(ModeloDeConjunto.Meta):
        indexes = [models.Index(fields=["conjunto", "subido_en"], name="reglamento_por_fecha")]

    def __str__(self):
        return self.nombre
