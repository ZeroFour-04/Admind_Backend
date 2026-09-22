from django.db import models

from apps.comun.modelos_base.modelos import ModeloDeConjunto


class Notificacion(ModeloDeConjunto):
    """Un aviso en la bandeja de una persona: la salida «aplicación» del canal."""

    persona = models.ForeignKey("personas.Persona", on_delete=models.PROTECT, related_name="notificaciones")
    titulo = models.CharField(max_length=120)
    cuerpo = models.TextField()
    # Qué la originó: el módulo y el id de su registro. Con esto, un mismo hecho avisa una sola vez.
    origen = models.CharField(max_length=30)
    referencia = models.UUIDField()
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta(ModeloDeConjunto.Meta):
        constraints = [
            *ModeloDeConjunto.Meta.constraints,
            models.UniqueConstraint(fields=["persona", "origen", "referencia"], name="notificacion_una_por_hecho"),
        ]
        indexes = [models.Index(fields=["conjunto", "persona", "-creada_en"], name="notificacion_bandeja")]

    def __str__(self):
        return f"{self.persona} · {self.titulo}"
