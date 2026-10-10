from django.db import models
from django.db.models import F, Q

from apps.comun.modelos_base.modelos import ModeloDeConjunto


class ModoDeUso(models.TextChoices):
    RESERVA = "reserva", "Con reserva"
    INGRESO = "ingreso", "Con ingreso"


class Area(ModeloDeConjunto):
    """Un área común del conjunto (HU-09), con reserva o con ingreso.

    Con reserva, sus franjas son bloques fijos desde la apertura (plan D1 a) y el calendario no se
    guarda: se calcula con el horario (maestro §5.1). Con ingreso no se aparta nada: vigilancia
    registra a quien entra y la permanencia máxima dice cuánto puede quedarse.
    """

    # Se redeclara la FK para que el related_name no choque con el Area de tests/aislamiento (plan P1).
    conjunto = models.ForeignKey("conjuntos.Conjunto", on_delete=models.PROTECT, related_name="areas")
    nombre = models.CharField(max_length=80)
    descripcion = models.TextField(blank=True)
    hora_apertura = models.TimeField()
    hora_cierre = models.TimeField()
    # Se elige al crear y no cambia (plan D4).
    modo_uso = models.CharField(max_length=10, choices=ModoDeUso.choices, default=ModoDeUso.RESERVA)
    # Solo en las áreas con reserva.
    duracion_franja_minutos = models.PositiveSmallIntegerField(null=True, blank=True)
    # Solo en las áreas con ingreso: cuánto puede quedarse una persona desde que entra.
    permanencia_maxima_minutos = models.PositiveSmallIntegerField(null=True, blank=True)
    # Cuántas personas caben. Es obligatorio: toda solicitud se compara con él.
    aforo_maximo = models.PositiveSmallIntegerField()
    en_mantenimiento = models.BooleanField(default=False)
    # Un área retirada se desactiva; no se borra (maestro §5.11).
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta(ModeloDeConjunto.Meta):
        constraints = [
            *ModeloDeConjunto.Meta.constraints,
            models.UniqueConstraint(fields=["conjunto", "nombre"], name="area_nombre_unico_en_conjunto"),
            models.CheckConstraint(condition=Q(hora_cierre__gt=F("hora_apertura")), name="area_horario_coherente"),
            models.CheckConstraint(
                condition=Q(duracion_franja_minutos__gte=120), name="area_duracion_franja_minima"
            ),
            models.CheckConstraint(condition=Q(aforo_maximo__gte=1), name="area_aforo_maximo_valido"),
            models.CheckConstraint(
                condition=Q(
                    modo_uso=ModoDeUso.RESERVA,
                    duracion_franja_minutos__isnull=False,
                    permanencia_maxima_minutos__isnull=True,
                )
                | Q(
                    modo_uso=ModoDeUso.INGRESO,
                    duracion_franja_minutos__isnull=True,
                    permanencia_maxima_minutos__isnull=False,
                ),
                name="area_modo_coherente",
            ),
        ]

    def __str__(self):
        return self.nombre
