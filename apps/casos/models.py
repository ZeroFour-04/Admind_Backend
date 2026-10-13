from django.db import models
from django.db.models import Q

from apps.comun.modelos_base.modelos import ModeloDeConjunto


class PrioridadCaso(models.TextChoices):
    BAJA = "BAJA", "Baja"
    NORMAL = "NORMAL", "Normal"
    ALTA = "ALTA", "Alta"
    URGENTE = "URGENTE", "Urgente"


class EstadoCaso(models.TextChoices):
    """El ciclo de un caso (HU-29). `RESUELTO` y `RECHAZADO` son terminales.

    `CITADO` existe porque el caso puede terminar en una cita con la administración, pero nada lo
    produce todavía: depende del módulo de citas (HU-31).
    """

    ABIERTO = "ABIERTO", "Por revisar"
    EN_REVISION = "EN_REVISION", "En revisión"
    REDIRIGIDO = "REDIRIGIDO", "Redirigido a Administración"
    CITADO = "CITADO", "Citado con Administración"
    RESUELTO = "RESUELTO", "Resuelto"
    RECHAZADO = "RECHAZADO", "Rechazado"


class CausalDeDescarte(models.TextChoices):
    """Por qué la Secretaría descarta un caso sin pasarlo al administrador. Lista cerrada, sin «otro»."""

    NO_ES_COMPETENCIA = "NO_ES_COMPETENCIA", "No es competencia de la administración"
    DUPLICADO = "DUPLICADO", "Caso duplicado"
    INFORMACION_INSUFICIENTE = "INFORMACION_INSUFICIENTE", "Información insuficiente"


ABIERTOS = [EstadoCaso.ABIERTO, EstadoCaso.EN_REVISION, EstadoCaso.REDIRIGIDO, EstadoCaso.CITADO]
# Mientras nadie lo redirige, el caso está en manos de la Secretaría.
EN_SECRETARIA = [EstadoCaso.ABIERTO, EstadoCaso.EN_REVISION]


class Caso(ModeloDeConjunto):
    titulo = models.CharField(max_length=120)
    cuerpo = models.TextField()
    estado = models.CharField(max_length=20, choices=EstadoCaso.choices, default=EstadoCaso.ABIERTO)
    # `NORMAL` la pone el sistema, también la base: un caso sin clasificar entra a la cola igual.
    prioridad = models.CharField(
        max_length=10, choices=PrioridadCaso.choices, default=PrioridadCaso.NORMAL, db_default=PrioridadCaso.NORMAL
    )
    justificacion_prioridad = models.TextField(blank=True)
    # Interna: de la Secretaría para el administrador. El residente no la ve.
    nota_redireccion = models.TextField(blank=True)
    # Lo que lee el residente al cerrarse el caso: la respuesta si se resolvió, el motivo si se rechazó.
    respuesta = models.TextField(blank=True)
    motivo_rechazo = models.TextField(blank=True)
    causal_rechazo = models.CharField(max_length=30, choices=CausalDeDescarte.choices, blank=True)
    autor = models.ForeignKey("personas.Persona", on_delete=models.PROTECT, related_name="casos")
    cerrado_por = models.ForeignKey(
        "personas.Persona", on_delete=models.PROTECT, null=True, blank=True, related_name="casos_cerrados"
    )
    cerrado_en = models.DateTimeField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta(ModeloDeConjunto.Meta):
        constraints = [
            *ModeloDeConjunto.Meta.constraints,
            models.CheckConstraint(condition=Q(estado__in=EstadoCaso.values), name="caso_estado_valido"),
            models.CheckConstraint(condition=Q(prioridad__in=PrioridadCaso.values), name="caso_prioridad_valida"),
            # `URGENTE` es el único nivel que cuesta algo escribir, y es el que se iba a inflar.
            models.CheckConstraint(
                condition=~Q(prioridad=PrioridadCaso.URGENTE) | ~Q(justificacion_prioridad=""),
                name="caso_urgente_con_justificacion",
            ),
            # La respuesta obligatoria: ningún caso se cierra sin algo escrito para el residente.
            models.CheckConstraint(
                condition=~Q(estado=EstadoCaso.RESUELTO) | ~Q(respuesta=""), name="caso_resuelto_con_respuesta"
            ),
            models.CheckConstraint(
                condition=~Q(estado=EstadoCaso.RECHAZADO) | ~Q(motivo_rechazo=""), name="caso_rechazado_con_motivo"
            ),
        ]
        indexes = [models.Index(fields=["conjunto", "-creado_en"], name="caso_bandeja")]

    def __str__(self):
        return self.titulo


class FotoDeCaso(ModeloDeConjunto):
    caso = models.OneToOneField(Caso, on_delete=models.PROTECT, related_name="foto")
    contenido = models.BinaryField()
    tipo = models.CharField(max_length=20)
