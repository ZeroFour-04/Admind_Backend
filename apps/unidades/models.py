from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.comun.aislamiento.managers import ManagerDeConjunto
from apps.comun.modelos_base.modelos import ModeloDeConjunto


class TipoDeVivienda(models.TextChoices):
    APARTAMENTO = "apartamento", "Apartamento"
    CASA = "casa", "Casa"


class Agrupacion(ModeloDeConjunto):
    """Lo que junta viviendas dentro del conjunto: una torre, un bloque, una manzana (HU-39).

    La palabra la pone el conjunto (`etiqueta`). `clave` es la etiqueta y el nombre sin tildes ni
    mayúsculas: con ella la base impide dos «Torre 1» aunque se escriban distinto.
    """

    etiqueta = models.CharField(max_length=30)
    nombre = models.CharField(max_length=40)
    clave = models.CharField(max_length=80)
    tipo_vivienda = models.CharField(max_length=12, choices=TipoDeVivienda.choices)
    # El orden de creación: «Torre 2» va antes que «Torre 10», cosa que el orden alfabético no da.
    orden = models.PositiveIntegerField()
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta(ModeloDeConjunto.Meta):
        constraints = [
            *ModeloDeConjunto.Meta.constraints,
            models.UniqueConstraint(fields=["conjunto", "clave"], name="agrupacion_clave_unica_en_conjunto"),
            models.CheckConstraint(
                condition=Q(tipo_vivienda__in=TipoDeVivienda.values), name="agrupacion_tipo_vivienda_valido"
            ),
        ]
        indexes = [models.Index(fields=["conjunto", "orden"], name="agrupacion_por_orden")]

    def __str__(self):
        return f"{self.etiqueta} {self.nombre}"


class Unidad(ModeloDeConjunto):
    """Una vivienda del conjunto, apartamento o casa (maestro §5.5, HU-39).

    Se nombra como la conoce el conjunto: «Torre 3 – Apto 402».
    """

    nombre = models.CharField(max_length=100)
    # Los cuatro vienen del generador (HU-39). Una unidad registrada a mano solo tiene nombre.
    tipo = models.CharField(max_length=12, choices=TipoDeVivienda.choices, default=TipoDeVivienda.APARTAMENTO)
    agrupacion = models.ForeignKey(
        Agrupacion, on_delete=models.PROTECT, null=True, blank=True, related_name="unidades"
    )
    numero = models.CharField(max_length=12, blank=True)
    piso = models.PositiveSmallIntegerField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta(ModeloDeConjunto.Meta):
        constraints = [
            *ModeloDeConjunto.Meta.constraints,
            models.UniqueConstraint(fields=["conjunto", "nombre"], name="unidad_nombre_unico_en_conjunto"),
            models.CheckConstraint(condition=Q(tipo__in=TipoDeVivienda.values), name="unidad_tipo_valido"),
        ]
        indexes = [models.Index(fields=["conjunto", "agrupacion"], name="unidad_por_agrupacion")]

    def __str__(self):
        return self.nombre


class TipoVinculo(models.TextChoices):
    PROPIETARIO = "propietario", "Propietario"
    ARRENDATARIO = "arrendatario", "Arrendatario"


class VinculoQuerySet(models.QuerySet):
    def vigentes(self):
        """Ya empezaron y no han terminado. `vigencia_hasta` es el primer día sin el vínculo."""
        hoy = timezone.localdate()
        return self.filter(vigencia_desde__lte=hoy).filter(
            Q(vigencia_hasta__isnull=True) | Q(vigencia_hasta__gt=hoy)
        )


class VinculoUnidad(ModeloDeConjunto):
    """La posición jurídica de una persona sobre una unidad (maestro §5.5). No es un rol.

    Un vínculo que termina se cierra con `vigencia_hasta`; no se borra.
    """

    persona = models.ForeignKey("personas.Persona", on_delete=models.PROTECT, related_name="vinculos")
    unidad = models.ForeignKey(Unidad, on_delete=models.PROTECT, related_name="vinculos")
    tipo = models.CharField(max_length=12, choices=TipoVinculo.choices)
    reside = models.BooleanField()
    vigencia_desde = models.DateField(default=timezone.localdate)
    vigencia_hasta = models.DateField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    objects = ManagerDeConjunto.from_queryset(VinculoQuerySet)()

    class Meta(ModeloDeConjunto.Meta):
        constraints = [
            *ModeloDeConjunto.Meta.constraints,
            models.CheckConstraint(condition=Q(tipo__in=TipoVinculo.values), name="vinculo_tipo_valido"),
            models.CheckConstraint(
                condition=Q(vigencia_hasta__isnull=True) | Q(vigencia_hasta__gte=F("vigencia_desde")),
                name="vinculo_vigencia_coherente",
            ),
            models.UniqueConstraint(
                fields=["unidad", "persona", "tipo"],
                condition=Q(vigencia_hasta__isnull=True),
                name="vinculo_vigente_unico",
            ),
        ]

    def __str__(self):
        return f"{self.persona} · {self.get_tipo_display()} de {self.unidad}"
