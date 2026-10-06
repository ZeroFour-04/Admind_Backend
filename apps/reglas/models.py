from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.comun.aislamiento.managers import ManagerDeConjunto
from apps.comun.modelos_base.modelos import ModeloDeConjunto
from apps.reglas.catalogo import TIPOS_ALFA, TIPOS_BETA, TipoDeRegla


class ReglaQuerySet(models.QuerySet):
    def vigentes(self, fecha=None):
        """Ya empezaron y no han terminado ese día. `vigencia_hasta` es el primer día sin la regla."""
        fecha = fecha or timezone.localdate()
        return self.filter(vigencia_desde__lte=fecha).filter(
            Q(vigencia_hasta__isnull=True) | Q(vigencia_hasta__gt=fecha)
        )

    def abiertas(self):
        """Las que nadie ha cerrado: vigentes hoy o por empezar. Solo puede haber una por tipo (P5)."""
        return self.filter(vigencia_hasta__isnull=True)


class Regla(ModeloDeConjunto):
    """Una regla del conjunto (alfa, sin área) o de un área (beta): tipo + parámetros + vigencia (HU-10).

    Editar no la cambia: la cierra y crea otra que la reemplaza (plan D4, versionado a). Así una
    solicitud evaluada con la versión 1 sigue explicándose cuando entra la versión 2.
    """

    # Vacía en las reglas del conjunto (alfa); obligatoria en las de un área (beta). Lo decide el tipo.
    area = models.ForeignKey("areas.Area", on_delete=models.PROTECT, null=True, blank=True, related_name="reglas")
    tipo = models.CharField(max_length=30, choices=TipoDeRegla.choices)
    parametros = models.JSONField()
    vigencia_desde = models.DateField(default=timezone.localdate)
    vigencia_hasta = models.DateField(null=True, blank=True)
    reemplaza = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="reemplazada_por"
    )
    creada_por = models.ForeignKey("personas.Persona", on_delete=models.PROTECT, related_name="reglas_creadas")
    creada_en = models.DateTimeField(auto_now_add=True)

    objects = ManagerDeConjunto.from_queryset(ReglaQuerySet)()

    class Meta(ModeloDeConjunto.Meta):
        constraints = [
            *ModeloDeConjunto.Meta.constraints,
            models.CheckConstraint(condition=Q(tipo__in=TipoDeRegla.values), name="regla_tipo_valido"),
            models.CheckConstraint(
                condition=Q(vigencia_hasta__isnull=True) | Q(vigencia_hasta__gte=F("vigencia_desde")),
                name="regla_vigencia_coherente",
            ),
            # Solo se exige a las abiertas: las cerradas son historial y conservan la forma que tuvieron.
            models.CheckConstraint(
                condition=Q(vigencia_hasta__isnull=False)
                | Q(tipo__in=TIPOS_ALFA, area__isnull=True)
                | Q(tipo__in=TIPOS_BETA, area__isnull=False),
                name="regla_nivel_coherente",
            ),
            models.UniqueConstraint(
                fields=["conjunto", "tipo"],
                condition=Q(vigencia_hasta__isnull=True, area__isnull=True),
                name="regla_alfa_unica_abierta",
            ),
            models.UniqueConstraint(
                fields=["conjunto", "area", "tipo"],
                condition=Q(vigencia_hasta__isnull=True, area__isnull=False),
                name="regla_beta_unica_abierta",
            ),
        ]
        indexes = [models.Index(fields=["conjunto", "area", "vigencia_desde"], name="regla_por_area")]

    def __str__(self):
        return f"{self.get_tipo_display()} · {self.area or 'conjunto'}"
