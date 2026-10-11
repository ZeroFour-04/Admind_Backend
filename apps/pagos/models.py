from django.db import models
from django.db.models import Q

from apps.comun.modelos_base.modelos import ModeloDeConjunto


class PagoDeAdministracion(ModeloDeConjunto):
    """Los hechos del pago de la administración de una vivienda en un mes (HU-35).

    Guarda quién reportó, quién confirmó y cuándo; el estado (`sin_reporte`, `reportado` o
    `confirmado`) se calcula de ahí y no se guarda: si alguien quita el check, no queda un
    estado viejo que corregir. No guarda monto ni saldo: el sistema no verifica el dinero.
    """

    unidad = models.ForeignKey("unidades.Unidad", on_delete=models.PROTECT, related_name="pagos_de_administracion")
    # Siempre el día 1 del mes (lo exige la base). En la API y en la URL viaja como AAAA-MM.
    periodo = models.DateField()
    reportado_por = models.ForeignKey(
        "personas.Persona", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    reportado_en = models.DateTimeField(null=True, blank=True)
    confirmado_por = models.ForeignKey(
        "personas.Persona", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    confirmado_en = models.DateTimeField(null=True, blank=True)

    class Meta(ModeloDeConjunto.Meta):
        constraints = [
            *ModeloDeConjunto.Meta.constraints,
            # Una fila por vivienda y mes: la decide la base, no una consulta previa.
            models.UniqueConstraint(fields=["conjunto", "unidad", "periodo"], name="pago_unico_por_vivienda_y_mes"),
            models.CheckConstraint(condition=Q(periodo__day=1), name="pago_periodo_es_dia_uno"),
            # Quién y cuándo van juntos: la base no acepta «confirmado» sin fecha ni «reportado» sin persona.
            models.CheckConstraint(
                condition=Q(confirmado_por__isnull=True, confirmado_en__isnull=True)
                | Q(confirmado_por__isnull=False, confirmado_en__isnull=False),
                name="pago_confirmado_completo",
            ),
            models.CheckConstraint(
                condition=Q(reportado_por__isnull=True, reportado_en__isnull=True)
                | Q(reportado_por__isnull=False, reportado_en__isnull=False),
                name="pago_reportado_completo",
            ),
        ]
        indexes = [models.Index(fields=["conjunto", "periodo"], name="pago_por_periodo")]

    def __str__(self):
        return f"{self.unidad} · {self.periodo:%Y-%m}"


class Comprobante(ModeloDeConjunto):
    """Un comprobante de un pago de administración, guardado dentro de la base (HU-35, plan P6).

    `tipo` es el que dice la firma del archivo, no el que dijo el navegador. Toda consulta de listado
    usa `defer("contenido")`: un `BinaryField` nunca se trae sin pedirlo.
    """

    pago = models.ForeignKey(PagoDeAdministracion, on_delete=models.PROTECT, related_name="comprobantes")
    contenido = models.BinaryField()
    tipo = models.CharField(max_length=20)
    nombre = models.CharField(max_length=120)
    peso = models.PositiveIntegerField()  # en bytes
    huella = models.CharField(max_length=64)  # SHA-256 del contenido
    subido_por = models.ForeignKey("personas.Persona", on_delete=models.PROTECT, related_name="+")
    subido_en = models.DateTimeField(auto_now_add=True)

    class Meta(ModeloDeConjunto.Meta):
        indexes = [models.Index(fields=["conjunto", "pago"], name="comprobante_pago_por_pago")]

    def __str__(self):
        return self.nombre
