from django.db import models
from django.db.models import Q

from apps.comun.modelos_base.modelos import ModeloDeConjunto


class EstadoCita(models.TextChoices):
    AGENDADA = "AGENDADA", "Agendada"
    ATENDIDA = "ATENDIDA", "Atendida"


class HorarioDeAtencion(ModeloDeConjunto):
    """Configuración semanal de atención del administrador (HU-31)."""

    dias = models.JSONField(default=list)
    actualizado_en = models.DateTimeField(auto_now=True)
    actualizado_por = models.ForeignKey("personas.Persona", on_delete=models.PROTECT)

    class Meta(ModeloDeConjunto.Meta):
        constraints = [
            *ModeloDeConjunto.Meta.constraints,
            models.UniqueConstraint(fields=["conjunto"], name="cita_horario_unico_conjunto"),
        ]


class Cita(ModeloDeConjunto):
    """Franja de dos horas agendada por un residente."""

    persona = models.ForeignKey("personas.Persona", on_delete=models.PROTECT, related_name="citas")
    fecha = models.DateField()
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()
    estado = models.CharField(max_length=12, choices=EstadoCita.choices, default=EstadoCita.AGENDADA)
    vence_en = models.DateTimeField()
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta(ModeloDeConjunto.Meta):
        constraints = [
            *ModeloDeConjunto.Meta.constraints,
            models.UniqueConstraint(
                fields=["conjunto", "persona"],
                condition=Q(estado=EstadoCita.AGENDADA),
                name="cita_unica_por_persona",
            ),
            models.UniqueConstraint(
                fields=["conjunto", "fecha", "hora_inicio"],
                condition=Q(estado=EstadoCita.AGENDADA),
                name="cita_franja_activa",
            ),
        ]
        indexes = [models.Index(fields=["conjunto", "fecha", "hora_inicio"], name="cita_fecha_hora")]
