import uuid

from django.db import models

from apps.comun.aislamiento.contexto import EscrituraEnOtroConjunto, conjunto_activo_id
from apps.comun.aislamiento.managers import ManagerDeConjunto


class ModeloDeConjunto(models.Model):
    """Base de toda tabla con datos de un conjunto (maestro §5.4).

    Las tablas globales de la lista cerrada no heredan de aquí.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conjunto = models.ForeignKey("conjuntos.Conjunto", on_delete=models.PROTECT)

    objects = ManagerDeConjunto()

    class Meta:
        abstract = True
        constraints = [
            models.UniqueConstraint(
                fields=["id", "conjunto"],
                name="%(app_label)s_%(class)s_id_conjunto",
            ),
        ]

    def save(self, *args, **kwargs):
        activo = conjunto_activo_id()
        if self.conjunto_id is None:
            self.conjunto_id = activo
        elif str(self.conjunto_id) != str(activo):
            raise EscrituraEnOtroConjunto("La fila pertenece a un conjunto distinto del activo.")
        super().save(*args, **kwargs)
