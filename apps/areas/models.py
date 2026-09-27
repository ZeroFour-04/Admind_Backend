from django.db import models
from django.db.models import F, Q

from apps.comun.modelos_base.modelos import ModeloDeConjunto


class Clasificacion(models.TextChoices):
    """Lista cerrada (HU-09). De ella sale si el área es esencial: la mora no aplica a esas (maestro §5.10)."""

    COMUN = "comun", "Común"
    COMUN_ESENCIAL = "comun_esencial", "Común esencial"
    COMUN_USO_EXCLUSIVO = "comun_uso_exclusivo", "Común de uso exclusivo"


class Area(ModeloDeConjunto):
    """Un área común reservable (HU-09). Sus franjas son bloques fijos desde la apertura (plan D1 a).

    El calendario no se guarda: las franjas se calculan con el horario (maestro §5.1).
    """

    # Se redeclara la FK para que el related_name no choque con el Area de tests/aislamiento (plan P1).
    conjunto = models.ForeignKey("conjuntos.Conjunto", on_delete=models.PROTECT, related_name="areas")
    nombre = models.CharField(max_length=80)
    descripcion = models.TextField(blank=True)
    clasificacion = models.CharField(max_length=20, choices=Clasificacion.choices)
    hora_apertura = models.TimeField()
    hora_cierre = models.TimeField()
    duracion_franja_minutos = models.PositiveSmallIntegerField()
    en_mantenimiento = models.BooleanField(default=False)
    # Un área retirada se desactiva; no se borra (maestro §5.11).
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta(ModeloDeConjunto.Meta):
        constraints = [
            *ModeloDeConjunto.Meta.constraints,
            models.UniqueConstraint(fields=["conjunto", "nombre"], name="area_nombre_unico_en_conjunto"),
            models.CheckConstraint(condition=Q(clasificacion__in=Clasificacion.values), name="area_clasificacion_valida"),
            models.CheckConstraint(condition=Q(hora_cierre__gt=F("hora_apertura")), name="area_horario_coherente"),
            models.CheckConstraint(condition=Q(duracion_franja_minutos__gt=0), name="area_duracion_franja_positiva"),
        ]

    @property
    def es_esencial(self):
        """Se deriva de la clasificación; no se guarda."""
        return self.clasificacion == Clasificacion.COMUN_ESENCIAL

    def __str__(self):
        return self.nombre
