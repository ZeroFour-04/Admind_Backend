from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models import F, Q

from apps.comun.modelos_base.modelos import ModeloDeConjunto


class EstadoIngreso(models.TextChoices):
    """`VENCIDO` es la salida que da el sistema al cumplirse el tiempo (plan P13)."""

    ADENTRO = "ADENTRO", "Adentro"
    SALIO = "SALIO", "Salió"
    VENCIDO = "VENCIDO", "Se cumplió el tiempo"


class Ingreso(ModeloDeConjunto):
    """Una persona adentro de una zona con ingreso (plan P7). No guarda el documento: solo la referencia a la persona.

    Un registro rechazado no deja fila. La evaluación se copia, como en `Solicitud`, para que la
    explicación siga siendo cierta aunque la regla cambie mañana.
    """

    area = models.ForeignKey("areas.Area", on_delete=models.PROTECT, related_name="ingresos")
    persona = models.ForeignKey("personas.Persona", on_delete=models.PROTECT, related_name="ingresos")
    unidad = models.ForeignKey("unidades.Unidad", on_delete=models.PROTECT, related_name="ingresos")
    # Cuántos entran con ella. Solo se guarda cuántos son, sin enlazarlos con los visitantes.
    acompanantes = models.PositiveSmallIntegerField(default=0)
    estado = models.CharField(max_length=10, choices=EstadoIngreso.choices, default=EstadoIngreso.ADENTRO)
    entrada_en = models.DateTimeField()
    # Queda guardada: cambiar la permanencia del área no la mueve (plan D9).
    salida_prevista_en = models.DateTimeField()
    salida_en = models.DateTimeField(null=True, blank=True)
    registrado_por = models.ForeignKey(
        "personas.Persona", on_delete=models.PROTECT, related_name="ingresos_registrados"
    )
    # Vacía en la salida automática: no tiene actor.
    salida_registrada_por = models.ForeignKey(
        "personas.Persona", on_delete=models.PROTECT, null=True, blank=True, related_name="salidas_registradas"
    )
    evaluacion = models.JSONField(null=True, blank=True, encoder=DjangoJSONEncoder)

    class Meta(ModeloDeConjunto.Meta):
        constraints = [
            *ModeloDeConjunto.Meta.constraints,
            # Un solo ingreso abierto por persona en el conjunto (plan D4). Lo decide la base.
            models.UniqueConstraint(
                fields=["conjunto", "persona"],
                condition=Q(estado=EstadoIngreso.ADENTRO),
                name="ingreso_uno_abierto_por_persona",
            ),
            models.CheckConstraint(condition=Q(estado__in=EstadoIngreso.values), name="ingreso_estado_valido"),
            models.CheckConstraint(
                condition=Q(salida_prevista_en__gt=F("entrada_en")), name="ingreso_salida_prevista_coherente"
            ),
            models.CheckConstraint(
                condition=Q(estado=EstadoIngreso.ADENTRO, salida_en__isnull=True)
                | (~Q(estado=EstadoIngreso.ADENTRO) & Q(salida_en__isnull=False)),
                name="ingreso_salida_segun_estado",
            ),
        ]
        indexes = [
            models.Index(fields=["conjunto", "area", "estado"], name="ingreso_por_area"),
            models.Index(fields=["conjunto", "estado", "salida_prevista_en"], name="ingreso_por_vencer"),
            models.Index(fields=["conjunto", "entrada_en"], name="ingreso_por_fecha"),
        ]

    def __str__(self):
        return f"{self.area} · {self.persona} · {self.get_estado_display()}"
