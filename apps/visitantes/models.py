from django.db import models
from django.db.models import F, Q

from apps.comun.modelos_base.modelos import ModeloDeConjunto


class Visitante(ModeloDeConjunto):
    """Una visita en portería. La salida se agrega como dato: la fila no se borra ni se reemplaza (HU-28)."""

    nombre = models.CharField(max_length=120)
    cedula = models.CharField(max_length=20)
    placa_vehiculo = models.CharField(max_length=10, blank=True)
    tipo_vehiculo = models.CharField(max_length=40, blank=True)
    unidad = models.ForeignKey("unidades.Unidad", on_delete=models.PROTECT, related_name="visitas")
    # El puesto de visitantes que ocupa mientras no tenga salida. La ocupación no es una tabla: es esto (plan P4).
    parqueadero = models.ForeignKey(
        "parqueaderos.Parqueadero", on_delete=models.PROTECT, null=True, blank=True, related_name="visitas"
    )
    hora_entrada = models.DateTimeField(auto_now_add=True)
    hora_salida = models.DateTimeField(null=True, blank=True)
    # Quién registró la salida. Vacío mientras la visita sigue adentro.
    salida_registrada_por = models.ForeignKey(
        "personas.Persona", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    class Meta(ModeloDeConjunto.Meta):
        constraints = [
            *ModeloDeConjunto.Meta.constraints,
            models.CheckConstraint(
                condition=Q(hora_salida__isnull=True) | Q(hora_salida__gte=F("hora_entrada")),
                name="visitante_salida_despues_de_entrada",
            ),
            # Un puesto lo ocupa una sola visita sin salida (R1). Al poner `hora_salida`, la fila sale del
            # índice y el puesto queda libre sin borrar nada. Lo decide la base, no una consulta previa.
            models.UniqueConstraint(
                fields=["conjunto", "parqueadero"],
                condition=Q(hora_salida__isnull=True, parqueadero__isnull=False),
                name="visitante_parqueadero_ocupado_unico",
            ),
        ]
        indexes = [
            models.Index(fields=["conjunto", "hora_entrada"], name="visitante_por_conjunto_hora"),
        ]

    def __str__(self):
        return f"{self.nombre} · {self.hora_entrada:%Y-%m-%d %H:%M}"
