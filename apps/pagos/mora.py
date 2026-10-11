"""La mora de una vivienda con la administración (HU-35, D9 a). No sabe quién pregunta.

`reglas` pregunta «¿está en mora?» sin saber cómo se responde, y este módulo responde sin saber
quién pregunta. Lo único que la mora toca es la regla *paz y salvo* (reservas e ingresos a zonas
comunes), que Administración enciende o no. El sistema no sanciona: no hay multas, intereses ni
bloqueos por mora (legal §4.2).

Un mes cuenta como vencido si ya pasó su día límite. La mora cuenta desde el mes en que el conjunto
definió por primera vez el día límite: una vivienda con algún mes vencido sin confirmar desde
entonces está en mora. Sin esa regla, ninguna lo está.
"""
from django.utils import timezone

from apps.comun.aislamiento.contexto import usar_conjunto
from apps.pagos import periodos
from apps.pagos.models import PagoDeAdministracion
from apps.reglas.catalogo import TipoDeRegla
from apps.reglas.models import Regla


def reglas_del_dia_limite():
    """Todas las versiones de la regla del conjunto activo, abiertas o cerradas."""
    return Regla.objects.filter(tipo=TipoDeRegla.DIA_LIMITE_DE_PAGO, area__isnull=True)


def dia_limite(hoy):
    """El `dia` de la regla DIA_LIMITE_DE_PAGO vigente hoy en el conjunto activo, o `None`."""
    regla = reglas_del_dia_limite().vigentes(hoy).order_by("-vigencia_desde", "-creada_en").first()
    return regla.parametros["dia"] if regla else None


def primer_periodo():
    """El mes de la `vigencia_desde` más antigua de cualquier versión de esa regla, o `None` (D9 a)."""
    regla = reglas_del_dia_limite().order_by("vigencia_desde").first()
    return regla.vigencia_desde.replace(day=1) if regla else None


def periodos_vencidos(hoy=None):
    """Los meses que ya debían estar pagados.

    Desde `primer_periodo` hasta el mes en curso si hoy pasó del día límite, o hasta el mes anterior
    si no (el día 10 todavía no hay mora; el 11 sí). Vacío sin regla.
    """
    hoy = hoy or timezone.localdate()
    dia = dia_limite(hoy)
    primero = primer_periodo()
    if dia is None or primero is None:
        return []
    actual = periodos.actual(hoy)
    ultimo = actual if hoy.day > dia else periodos.sumar_meses(actual, -1)
    return periodos.entre(primero, ultimo)


def unidad_en_mora(unidad, hoy=None):
    """Si a la vivienda le falta el check en alguno de los meses vencidos.

    Cuenta los pagos confirmados de la vivienda dentro de esos meses y compara con cuántos son. Un
    mes sin fila o sin check cuenta como no pagado. La mora se calcula en el conjunto de la vivienda:
    dentro de una petición es el activo, y fuera de ella (una prueba, un proceso) no hace falta fijarlo.
    """
    with usar_conjunto(unidad.conjunto_id):
        vencidos = periodos_vencidos(hoy)
        if not vencidos:
            return False
        confirmados = PagoDeAdministracion.objects.filter(
            unidad=unidad, periodo__in=vencidos, confirmado_por__isnull=False
        ).count()
        return confirmados < len(vencidos)
