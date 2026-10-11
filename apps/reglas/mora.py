"""Si una unidad está en mora (plan D5 b, P9). El punto por donde `reglas` mira hacia `pagos`.

La respuesta real la da `apps/pagos/mora.py` (HU-35): una vivienda está en mora si le falta el pago
confirmado de algún mes vencido desde que el conjunto definió el día límite de pago. Esta función
conserva su firma, así que los evaluadores de reservas y de ingresos no cambian.
"""


def unidad_en_mora(unidad):
    # El import va aquí adentro a propósito: `pagos` lee reglas y `reglas` pregunta por pagos. Hecho al
    # cargar el módulo sería una dependencia circular; tardío, este archivo sigue siendo el único punto
    # por donde `reglas` mira hacia afuera.
    from apps.pagos import mora

    return mora.unidad_en_mora(unidad)
