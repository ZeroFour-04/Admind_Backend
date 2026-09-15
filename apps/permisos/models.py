import uuid

from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.permisos.catalogo import ROLES_DE_CONJUNTO, ROLES_DE_PLATAFORMA, Rol


class Asignacion(models.Model):
    """Un rol del catálogo para una persona en un conjunto. Retirarlo es cerrar la vigencia, no borrar."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    persona = models.ForeignKey(
        "personas.Persona",
        on_delete=models.PROTECT,
        related_name="asignaciones",
    )
    rol = models.CharField(max_length=30, choices=Rol.choices)
    # Nulo solo para los roles de plataforma (maestro §5.3).
    conjunto = models.ForeignKey(
        "conjuntos.Conjunto",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="asignaciones",
    )
    vigencia_desde = models.DateField(default=timezone.localdate)
    vigencia_hasta = models.DateField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(rol__in=sorted(ROLES_DE_PLATAFORMA), conjunto__isnull=True)
                    | Q(rol__in=sorted(ROLES_DE_CONJUNTO), conjunto__isnull=False)
                ),
                name="asignacion_conjunto_segun_alcance",
            ),
            models.CheckConstraint(
                condition=Q(vigencia_hasta__isnull=True) | Q(vigencia_hasta__gte=F("vigencia_desde")),
                name="asignacion_vigencia_coherente",
            ),
            models.UniqueConstraint(
                fields=["persona", "rol", "conjunto"],
                condition=Q(vigencia_hasta__isnull=True),
                nulls_distinct=False,
                name="asignacion_vigente_unica",
            ),
        ]

    def __str__(self):
        return f"{self.persona} · {self.get_rol_display()}"
