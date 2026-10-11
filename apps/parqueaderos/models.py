from django.db import models
from django.db.models import Q

from apps.comun.modelos_base.modelos import ModeloDeConjunto


class TipoDeParqueadero(models.TextChoices):
    RESIDENTES = "residentes", "Residentes"
    VISITANTES = "visitantes", "Visitantes"


class Parqueadero(ModeloDeConjunto):
    """Un puesto de parqueo del conjunto, con su código (HU-28; HU-34 asignará los de residentes).

    La ocupación de uno de visitantes no es una tabla: es el parqueadero de una visita que todavía no
    tiene salida (`Visitante.parqueadero`). Aquí no existe ninguna asignación a una unidad.
    """

    codigo = models.CharField(max_length=20)
    tipo = models.CharField(max_length=12, choices=TipoDeParqueadero.choices)
    accesible = models.BooleanField(default=False)
    notas = models.CharField(max_length=200, blank=True)
    # Retirar es baja lógica: el historial de las visitas sigue apuntando a él (maestro §5.11).
    activo = models.BooleanField(default=True)
    creado_por = models.ForeignKey("personas.Persona", on_delete=models.PROTECT, related_name="+")
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta(ModeloDeConjunto.Meta):
        constraints = [
            *ModeloDeConjunto.Meta.constraints,
            # El código se guarda en mayúsculas (`save`), así que «v-01» y «V-01» chocan aquí.
            models.UniqueConstraint(fields=["conjunto", "codigo"], name="parqueadero_codigo_unico"),
            models.CheckConstraint(condition=Q(tipo__in=TipoDeParqueadero.values), name="parqueadero_tipo_valido"),
        ]

    def save(self, *args, **kwargs):
        self.codigo = self.codigo.strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.codigo
