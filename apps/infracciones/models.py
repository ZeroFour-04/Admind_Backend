from django.db import models
from django.db.models import Q

from apps.comun.modelos_base.modelos import ModeloDeConjunto


class RegistroDeInfraccion(ModeloDeConjunto):
    """El registro de que se comunicó una infracción a la vivienda (HU-30; maestro §5.8).

    El sistema **no sanciona**: deja constancia de un hecho y de que se les avisó a quienes tienen un vínculo
    con la vivienda, y de cómo terminó. Por eso no hay campo de sanción, multa ni restricción de uso (legal
    §4.2, L675 arts. 59 y 60): imponerla es de la asamblea o del consejo y ocurre fuera de AdMind.

    Tampoco hay campo `estado`: está abierto mientras `cierre_fecha` es nulo, y un solo dato no se contradice
    con otro. `fecha_notificacion` es obligatoria en la base: no existe un registro que no se haya comunicado.
    Un registro equivocado se anula (solo el Superusuario), no se borra.
    """

    unidad = models.ForeignKey("unidades.Unidad", on_delete=models.PROTECT, related_name="infracciones")
    # Opcional: la infracción puede nacer de un caso (D1 a), pero el caso no guarda la vivienda.
    caso = models.ForeignKey("casos.Caso", on_delete=models.PROTECT, null=True, blank=True, related_name="infracciones")
    descripcion_hecho = models.TextField()
    fecha_hecho = models.DateField()
    registrado_por = models.ForeignKey("personas.Persona", on_delete=models.PROTECT, related_name="+")
    registrado_en = models.DateTimeField(auto_now_add=True)
    # NOT NULL a propósito: sin comunicación no hay registro.
    fecha_notificacion = models.DateTimeField()
    cierre_fecha = models.DateTimeField(null=True, blank=True)
    cierre_comentario = models.TextField(null=True, blank=True)
    cerrado_por = models.ForeignKey("personas.Persona", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    anulado = models.BooleanField(default=False)
    anulacion_motivo = models.TextField(blank=True, default="")
    anulado_por = models.ForeignKey("personas.Persona", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    anulado_en = models.DateTimeField(null=True, blank=True)

    class Meta(ModeloDeConjunto.Meta):
        constraints = [
            *ModeloDeConjunto.Meta.constraints,
            models.CheckConstraint(condition=~Q(descripcion_hecho=""), name="infraccion_hecho_descrito"),
            # La fecha y el comentario del cierre van juntos, y el comentario no puede ser vacío.
            models.CheckConstraint(
                condition=(Q(cierre_fecha__isnull=True) & Q(cierre_comentario__isnull=True))
                | (Q(cierre_fecha__isnull=False) & Q(cierre_comentario__isnull=False) & ~Q(cierre_comentario="")),
                name="infraccion_cierre_completo",
            ),
            # Anular exige el motivo, quién y cuándo.
            models.CheckConstraint(
                condition=Q(anulado=False)
                | (~Q(anulacion_motivo="") & Q(anulado_por__isnull=False) & Q(anulado_en__isnull=False)),
                name="infraccion_anulacion_completa",
            ),
        ]
        indexes = [
            models.Index(fields=["conjunto", "unidad"], name="infraccion_por_unidad"),
            models.Index(fields=["conjunto", "-registrado_en"], name="infraccion_reciente"),
        ]

    @property
    def abierto(self):
        return self.cierre_fecha is None and not self.anulado

    def __str__(self):
        return f"{self.unidad} · {self.fecha_hecho}"
