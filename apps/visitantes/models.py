from django.db import models

from apps.comun.modelos_base.modelos import ModeloDeConjunto


class Visitante(ModeloDeConjunto):
    nombre = models.CharField(max_length=120)
    cedula = models.CharField(max_length=20)
    placa_vehiculo = models.CharField(max_length=10, blank=True)
    tipo_vehiculo = models.CharField(max_length=40, blank=True)
    unidad = models.ForeignKey("unidades.Unidad", on_delete=models.PROTECT, related_name="visitas")
    hora_entrada = models.DateTimeField(auto_now_add=True)

    class Meta(ModeloDeConjunto.Meta):
        indexes = [
            models.Index(fields=["conjunto", "hora_entrada"], name="visitante_por_conjunto_hora"),
        ]

    def __str__(self):
        return f"{self.nombre} · {self.hora_entrada:%Y-%m-%d %H:%M}"
