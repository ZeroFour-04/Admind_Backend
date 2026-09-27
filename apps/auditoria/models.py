from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

from apps.comun.aislamiento.managers import ManagerDeConjunto
from apps.comun.modelos_base.modelos import ModeloDeConjunto


class RegistroInmutable(Exception):
    """Se intentó modificar o borrar un registro de auditoría: es de solo inserción (maestro §5.11)."""


class RegistroQuerySet(models.QuerySet):
    """Sin `update()` ni `delete()`: se saltarían `save()` y `delete()` del modelo."""

    def update(self, **kwargs):
        raise RegistroInmutable("La auditoría no se modifica.")

    def delete(self):
        raise RegistroInmutable("La auditoría no se borra.")


class Registro(ModeloDeConjunto):
    """Quién hizo qué, cuándo, y cómo estaba antes y después (maestro §5.3, §5.11).

    El solo inserción vive por ahora en el código. Quitarle UPDATE y DELETE al usuario de base
    de datos queda para cuando haya dos usuarios de BD (maestro §11.5).
    """

    actor = models.ForeignKey("personas.Persona", on_delete=models.PROTECT, related_name="registros_de_auditoria")
    accion = models.CharField(max_length=60)  # p. ej. "rol.asignar"
    entidad = models.CharField(max_length=60)  # p. ej. "Asignacion"
    entidad_id = models.UUIDField(null=True, blank=True)
    antes = models.JSONField(null=True, blank=True, encoder=DjangoJSONEncoder)
    despues = models.JSONField(null=True, blank=True, encoder=DjangoJSONEncoder)
    detalle = models.JSONField(null=True, blank=True, encoder=DjangoJSONEncoder)
    via_superusuario = models.BooleanField(default=False)
    creado_en = models.DateTimeField(auto_now_add=True)

    objects = ManagerDeConjunto.from_queryset(RegistroQuerySet)()

    class Meta(ModeloDeConjunto.Meta):
        indexes = [
            models.Index(fields=["conjunto", "-creado_en"], name="auditoria_reciente"),
            models.Index(fields=["conjunto", "actor", "accion", "creado_en"], name="auditoria_por_actor"),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RegistroInmutable("La auditoría no se modifica.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RegistroInmutable("La auditoría no se borra.")

    def __str__(self):
        return f"{self.accion} · {self.entidad}"
