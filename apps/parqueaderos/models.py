from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.comun.modelos_base.modelos import ModeloDeConjunto


class TipoDeParqueadero(models.TextChoices):
    RESIDENTES = "residentes", "Residentes"
    VISITANTES = "visitantes", "Visitantes"


class TipoDeVehiculo(models.TextChoices):
    CARRO = "carro", "Carro"
    MOTO = "moto", "Moto"
    BICICLETA = "bicicleta", "Bicicleta"


class Parqueadero(ModeloDeConjunto):
    """Un puesto de parqueo del conjunto, con su código (HU-28; HU-34 asigna los de residentes).

    La ocupación de uno de visitantes no es una tabla: es el parqueadero de una visita que todavía no
    tiene salida (`Visitante.parqueadero`). La de uno de residentes sí: es su `AsignacionParqueadero`
    vigente. Los de visitantes no se asignan nunca.
    """

    codigo = models.CharField(max_length=20)
    tipo = models.CharField(max_length=12, choices=TipoDeParqueadero.choices)
    # Para qué vehículo es el puesto: con él se cuenta el tope por vivienda (HU-34, D2). `db_default` para
    # que las filas que ya existían queden en «carro» sin que la migración las recorra.
    vehiculo = models.CharField(
        max_length=10, choices=TipoDeVehiculo.choices, default=TipoDeVehiculo.CARRO, db_default=TipoDeVehiculo.CARRO
    )
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
            models.CheckConstraint(condition=Q(vehiculo__in=TipoDeVehiculo.values), name="parqueadero_vehiculo_valido"),
        ]

    def save(self, *args, **kwargs):
        self.codigo = self.codigo.strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.codigo


class AsignacionParqueadero(ModeloDeConjunto):
    """Un parqueadero de residentes destinado a una vivienda, desde cuándo y hasta cuándo (HU-34).

    Registra un hecho administrativo, no constituye un derecho. Cerrarla es poner `vigencia_hasta`, nunca
    borrar: el historial responde «¿desde cuándo parquea ahí?». No existe ninguna operación que la cierre
    como sanción ni por mora (legal §4.2): solo se reasigna a otra vivienda o se libera.
    """

    parqueadero = models.ForeignKey(Parqueadero, on_delete=models.PROTECT, related_name="asignaciones")
    unidad = models.ForeignKey("unidades.Unidad", on_delete=models.PROTECT, related_name="asignaciones_de_parqueadero")
    vigencia_desde = models.DateField(default=timezone.localdate)
    vigencia_hasta = models.DateField(null=True, blank=True)
    registrado_por = models.ForeignKey("personas.Persona", on_delete=models.PROTECT, related_name="+")
    registrado_en = models.DateTimeField(auto_now_add=True)
    # Quién la cerró (reasignó o liberó). Vacío mientras sigue vigente.
    cerrado_por = models.ForeignKey("personas.Persona", on_delete=models.PROTECT, null=True, blank=True, related_name="+")

    class Meta(ModeloDeConjunto.Meta):
        constraints = [
            *ModeloDeConjunto.Meta.constraints,
            # Un puesto, una asignación vigente. Lo decide la base: dos peticiones a la vez no se la saltan.
            models.UniqueConstraint(
                fields=["conjunto", "parqueadero"],
                condition=Q(vigencia_hasta__isnull=True),
                name="asignacion_parqueadero_vigente_unica",
            ),
            models.CheckConstraint(
                condition=Q(vigencia_hasta__isnull=True) | Q(vigencia_hasta__gte=F("vigencia_desde")),
                name="asignacion_parqueadero_vigencia_coherente",
            ),
        ]
        indexes = [models.Index(fields=["conjunto", "unidad"], name="asignacion_parqueadero_unidad")]

    def __str__(self):
        return f"{self.parqueadero} → {self.unidad}"
