from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models import F, Q

from apps.comun.modelos_base.modelos import ModeloDeConjunto


class EstadoSolicitud(models.TextChoices):
    """Los estados de una solicitud (maestro §5.1). El estado vive aquí, no en la franja.

    `LIBERADA` es nuevo (plan D2 a): el bloqueo se soltó a propósito o porque las reglas rechazaron
    la solicitud. Se distingue de `EXPIRADA` porque solo el vencimiento gasta oportunidad (R9).
    """

    EN_SOLICITUD = "EN_SOLICITUD", "En trámite"
    APARTADA = "APARTADA", "Apartada"
    RESERVADA = "RESERVADA", "Reservada"
    RECHAZADA = "RECHAZADA", "Rechazada"
    CANCELADA = "CANCELADA", "Cancelada"
    EXPIRADA = "EXPIRADA", "Expirada"
    LIBERADA = "LIBERADA", "Liberada"


class MotivoLiberacion(models.TextChoices):
    VOLUNTARIA = "voluntaria", "La persona la soltó"
    REGLAS = "reglas", "No cumplió las reglas"


class CategoriaDeRechazo(models.TextChoices):
    """Por qué se rechazó una solicitud. Dos listas cerradas en una sola columna (HU-14).

    De fondo, las de Administración: decide si la reserva se concede, y por eso tiene `OTRO`.
    De forma, las de Secretaría: la solicitud no está en condiciones de tramitarse. Sin `OTRO`.
    """

    NO_DISPONIBLE = "NO_DISPONIBLE", "El área no está disponible"
    CONDICIONES_NO_CUMPLIDAS = "CONDICIONES_NO_CUMPLIDAS", "No se cumplen las condiciones"
    DOCUMENTACION_INCOMPLETA = "DOCUMENTACION_INCOMPLETA", "Documentación incompleta"
    INCUMPLE_REGLAMENTO = "INCUMPLE_REGLAMENTO", "Incumple el reglamento"
    OTRO = "OTRO", "Otro motivo"
    DATOS_INCOMPLETOS = "DATOS_INCOMPLETOS", "Datos incompletos"
    SOLICITUD_DUPLICADA = "SOLICITUD_DUPLICADA", "Solicitud duplicada"
    VIVIENDA_NO_CORRESPONDE = "VIVIENDA_NO_CORRESPONDE", "La vivienda no corresponde"


CATEGORIAS_DE_FONDO = [
    CategoriaDeRechazo.NO_DISPONIBLE,
    CategoriaDeRechazo.CONDICIONES_NO_CUMPLIDAS,
    CategoriaDeRechazo.DOCUMENTACION_INCOMPLETA,
    CategoriaDeRechazo.INCUMPLE_REGLAMENTO,
    CategoriaDeRechazo.OTRO,
]
CAUSALES_DE_FORMA = [
    CategoriaDeRechazo.DATOS_INCOMPLETOS,
    CategoriaDeRechazo.SOLICITUD_DUPLICADA,
    CategoriaDeRechazo.VIVIENDA_NO_CORRESPONDE,
]

BLOQUEANTES = [EstadoSolicitud.EN_SOLICITUD, EstadoSolicitud.APARTADA, EstadoSolicitud.RESERVADA]
# Hasta aquí la solicitud puede no tener unidad: se elige al llenar el formulario.
SIN_UNIDAD_PERMITIDA = [EstadoSolicitud.EN_SOLICITUD, EstadoSolicitud.EXPIRADA, EstadoSolicitud.LIBERADA]


class Solicitud(ModeloDeConjunto):
    """Una solicitud de reserva sobre una franja `(área, fecha, hora_inicio, hora_fin)` (maestro §5.1, HU-11)."""

    area = models.ForeignKey("areas.Area", on_delete=models.PROTECT, related_name="solicitudes")
    unidad = models.ForeignKey(
        "unidades.Unidad", on_delete=models.PROTECT, null=True, blank=True, related_name="solicitudes"
    )
    persona = models.ForeignKey("personas.Persona", on_delete=models.PROTECT, related_name="solicitudes")
    fecha = models.DateField()
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()
    estado = models.CharField(max_length=20, choices=EstadoSolicitud.choices, default=EstadoSolicitud.EN_SOLICITUD)
    bloqueo_vence_en = models.DateTimeField()
    motivo_liberacion = models.CharField(max_length=12, choices=MotivoLiberacion.choices, blank=True)
    motivo = models.CharField(max_length=200, blank=True)
    asistentes = models.PositiveIntegerField(null=True, blank=True)
    observaciones = models.TextField(blank=True)
    # Copia de cada regla evaluada al enviar (plan P10): explica el resultado aunque la regla cambie después.
    evaluacion = models.JSONField(null=True, blank=True, encoder=DjangoJSONEncoder)
    evaluada_en = models.DateTimeField(null=True, blank=True)
    motivo_decision = models.TextField(blank=True)
    # Solo en una rechazada: la categoría de Administración o la causal formal de Secretaría.
    categoria_rechazo = models.CharField(max_length=30, choices=CategoriaDeRechazo.choices, blank=True)
    decidida_por = models.ForeignKey(
        "personas.Persona", on_delete=models.PROTECT, null=True, blank=True, related_name="decisiones_reserva"
    )
    decidida_en = models.DateTimeField(null=True, blank=True)
    # El pago lo declara una persona de la administración; el sistema no verifica el dinero (HU-16).
    pago_declarado_por = models.ForeignKey(
        "personas.Persona",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="pagos_de_reserva_declarados",
    )
    pago_declarado_en = models.DateTimeField(null=True, blank=True)
    creada_en = models.DateTimeField(auto_now_add=True)
    enviada_en = models.DateTimeField(null=True, blank=True)

    class Meta(ModeloDeConjunto.Meta):
        constraints = [
            *ModeloDeConjunto.Meta.constraints,
            # Una sola solicitud bloqueante por franja (R7). Es la que decide la concurrencia.
            models.UniqueConstraint(
                fields=["conjunto", "area", "fecha", "hora_inicio"],
                condition=Q(estado__in=BLOQUEANTES),
                name="solicitud_franja_bloqueante_unica",
            ),
            # Un solo bloqueo activo por persona en el conjunto (plan D3 a).
            models.UniqueConstraint(
                fields=["conjunto", "persona"],
                condition=Q(estado=EstadoSolicitud.EN_SOLICITUD),
                name="solicitud_un_bloqueo_por_persona",
            ),
            models.CheckConstraint(condition=Q(hora_fin__gt=F("hora_inicio")), name="solicitud_horario_coherente"),
            models.CheckConstraint(condition=Q(estado__in=EstadoSolicitud.values), name="solicitud_estado_valido"),
            models.CheckConstraint(
                condition=Q(estado__in=SIN_UNIDAD_PERMITIDA) | Q(unidad__isnull=False),
                name="solicitud_unidad_desde_apartada",
            ),
            # Quién declaró y cuándo van juntos: la base no acepta uno sin el otro (HU-16).
            models.CheckConstraint(
                condition=Q(pago_declarado_por__isnull=True, pago_declarado_en__isnull=True)
                | Q(pago_declarado_por__isnull=False, pago_declarado_en__isnull=False),
                name="solicitud_pago_declarado_completo",
            ),
            models.CheckConstraint(
                condition=Q(categoria_rechazo="") | Q(categoria_rechazo__in=CategoriaDeRechazo.values),
                name="solicitud_categoria_de_rechazo_valida",
            ),
            # Un rechazo sin categoría no se guarda, aunque el código lo intente (HU-14).
            models.CheckConstraint(
                condition=~Q(estado=EstadoSolicitud.RECHAZADA) | ~Q(categoria_rechazo=""),
                name="solicitud_rechazada_con_categoria",
            ),
        ]
        indexes = [
            models.Index(fields=["conjunto", "area", "fecha"], name="solicitud_por_franja"),
            models.Index(fields=["conjunto", "estado", "bloqueo_vence_en"], name="solicitud_por_vencer"),
        ]

    def __str__(self):
        return f"{self.area} · {self.fecha} {self.hora_inicio:%H:%M} · {self.get_estado_display()}"


class Campana(ModeloDeConjunto):
    """Suscripción a una franja concreta: si vuelve a quedar libre, avisa a la persona.

    La franja queda marcada como activa; al notificarse, se desactiva para no volver a avisar por el
    mismo hueco.
    """

    area = models.ForeignKey("areas.Area", on_delete=models.PROTECT, related_name="campanas")
    persona = models.ForeignKey("personas.Persona", on_delete=models.PROTECT, related_name="campanas_reserva")
    fecha = models.DateField()
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()
    activa = models.BooleanField(default=True)
    creada_en = models.DateTimeField(auto_now_add=True)
    notificada_en = models.DateTimeField(null=True, blank=True)

    class Meta(ModeloDeConjunto.Meta):
        constraints = [
            *ModeloDeConjunto.Meta.constraints,
            models.UniqueConstraint(
                fields=["conjunto", "persona", "area", "fecha", "hora_inicio", "hora_fin"],
                condition=Q(activa=True),
                name="campana_activa_unica_por_franja",
            ),
        ]
        indexes = [models.Index(fields=["conjunto", "area", "fecha", "hora_inicio"], name="campana_por_franja")]

    def __str__(self):
        return f"{self.persona} · {self.area} · {self.fecha} {self.hora_inicio:%H:%M}"


class ComprobanteDePago(ModeloDeConjunto):
    """Un comprobante del pago de una reserva, guardado dentro de la base (HU-16, plan D5 a).

    Lo sube quien declara el pago o el residente dueño de la solicitud. `tipo` es el que dice la firma
    del archivo, no el que dijo el navegador. Toda consulta de listado usa `defer("contenido")`.
    """

    solicitud = models.ForeignKey(Solicitud, on_delete=models.PROTECT, related_name="comprobantes")
    contenido = models.BinaryField()
    tipo = models.CharField(max_length=20)
    nombre = models.CharField(max_length=120)
    peso = models.PositiveIntegerField()  # en bytes
    huella = models.CharField(max_length=64)  # SHA-256 del contenido
    subido_por = models.ForeignKey("personas.Persona", on_delete=models.PROTECT, related_name="+")
    subido_en = models.DateTimeField(auto_now_add=True)

    class Meta(ModeloDeConjunto.Meta):
        indexes = [models.Index(fields=["conjunto", "solicitud"], name="comprobante_por_solicitud")]

    def __str__(self):
        return self.nombre
