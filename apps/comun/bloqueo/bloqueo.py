"""Mecanismo compartido de recurso limitado y concurrencia (R1, maestro §5.1).

No importa ninguna app de negocio. La exclusión la garantiza el índice único parcial que cada
app declara en su migración: aquí solo se traduce su violación y se expira lo vencido.
"""
from django.db import IntegrityError, transaction


class RecursoOcupado(Exception):
    """Otro ya tiene el recurso. `restriccion` es el índice único que lo impidió."""

    def __init__(self, restriccion):
        super().__init__(restriccion)
        self.restriccion = restriccion


def nombre_de_la_restriccion(error):
    diagnostico = getattr(error.__cause__, "diag", None)
    return getattr(diagnostico, "constraint_name", None) or str(error)


def tomar(crear):
    """Corre `crear()` en su propia transacción. Si choca con un índice único, lanza `RecursoOcupado`.

    No se consulta antes si el recurso está libre: entre esa consulta y el INSERT otro podría
    tomarlo. La base decide, y decide una sola vez.
    """
    try:
        with transaction.atomic():
            return crear()
    except IntegrityError as error:
        raise RecursoOcupado(nombre_de_la_restriccion(error)) from error


def expirar_vencidos(queryset, *, campo_vence, estado_activo, estado_expirado, ahora):
    """Pasa a expirado todo lo activo que ya venció, con un solo UPDATE. Devuelve cuántos expiró.

    Se llama al siguiente acceso, no desde un proceso en segundo plano. Es idempotente: lo que
    ya no está activo (expirado, liberado o enviado) no se vuelve a tocar.
    """
    return queryset.filter(estado=estado_activo, **{f"{campo_vence}__lte": ahora}).update(estado=estado_expirado)
