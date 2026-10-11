"""Meses del pago de administración (HU-35): funciones puras, sin base de datos.

Un periodo es un mes. En la base es un `date` con el día 1; en la API y en la URL viaja como `AAAA-MM`.
"""
from datetime import date

from django.utils import timezone

# Un año fuera de este rango es un error de escritura, no un mes que alguien quiera abrir.
PRIMER_ANIO, ULTIMO_ANIO = 2000, 2100


def periodo_de(texto):
    """«2026-10» → `date(2026, 10, 1)`. `ValueError` si no sirve."""
    if not isinstance(texto, str):
        raise ValueError("El periodo va como AAAA-MM.")
    partes = texto.strip().split("-")
    if len(partes) != 2 or len(partes[0]) != 4 or len(partes[1]) != 2 or not all(p.isdigit() for p in partes):
        raise ValueError("El periodo va como AAAA-MM, por ejemplo 2026-10.")
    anio, mes = int(partes[0]), int(partes[1])
    if not PRIMER_ANIO <= anio <= ULTIMO_ANIO or not 1 <= mes <= 12:
        raise ValueError("Ese mes no existe.")
    return date(anio, mes, 1)


def texto_de(periodo):
    """`date(2026, 10, 1)` → «2026-10»."""
    return f"{periodo.year:04d}-{periodo.month:02d}"


def actual(hoy=None):
    """El día 1 del mes de hoy."""
    hoy = hoy or timezone.localdate()
    return hoy.replace(day=1)


def sumar_meses(periodo, n):
    """El mes `n` meses después (o antes, con `n` negativo), siempre el día 1."""
    indice = periodo.year * 12 + (periodo.month - 1) + n
    return date(indice // 12, indice % 12 + 1, 1)


def entre(desde, hasta):
    """Todos los meses de `desde` a `hasta`, ambos incluidos. Vacío si `hasta` es anterior."""
    meses, mes = [], desde
    while mes <= hasta:
        meses.append(mes)
        mes = sumar_meses(mes, 1)
    return meses
