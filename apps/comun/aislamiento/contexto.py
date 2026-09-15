"""Conjunto activo de la operación en curso (maestro §5.4).

En una petición lo fija el middleware a partir de la sesión. Fuera de una petición (pruebas, procesos
de plataforma) se fija a mano con `usar_conjunto`.
"""
import uuid
from contextlib import contextmanager
from contextvars import ContextVar

_conjunto_activo = ContextVar("conjunto_activo", default=None)


class SinConjuntoActivo(Exception):
    """Se tocó una tabla de conjunto sin conjunto activo. Es un error de programación."""


class EscrituraEnOtroConjunto(Exception):
    """Se intentó guardar una fila en un conjunto distinto del activo."""


def conjunto_activo_id():
    conjunto_id = _conjunto_activo.get()
    if conjunto_id is None:
        raise SinConjuntoActivo("No hay conjunto activo.")
    return conjunto_id


@contextmanager
def usar_conjunto(conjunto_id):
    token = _conjunto_activo.set(uuid.UUID(str(conjunto_id)))
    try:
        yield
    finally:
        _conjunto_activo.reset(token)
