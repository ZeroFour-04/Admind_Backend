from django.db import models

from apps.comun.aislamiento.contexto import conjunto_activo_id


class ManagerDeConjunto(models.Manager):
    """Toda consulta sale filtrada por el conjunto activo (maestro §5.4). Sin conjunto activo, falla."""

    def get_queryset(self):
        return super().get_queryset().filter(conjunto_id=conjunto_activo_id())
