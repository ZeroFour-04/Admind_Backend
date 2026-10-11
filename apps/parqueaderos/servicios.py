"""Catálogo de parqueaderos del conjunto activo (HU-28). No sabe nada de HTTP.

Toda escritura deja registro en la auditoría. Aquí no existe ninguna operación que asigne un
parqueadero a una unidad: la asignación de los de residentes es HU-34, y los de visitantes
nunca se asignan (maestro §4.2, §5.6).
"""
from django.db import IntegrityError, transaction
from django.db.models import Count, Q

from apps.auditoria import servicios as auditoria
from apps.parqueaderos.models import Parqueadero


class CodigoRepetido(Exception):
    """Ya hay un parqueadero con ese código en el conjunto."""


class ParqueaderoNoEncontrado(Exception):
    """No existe en el conjunto activo o ya estaba retirado."""


class ParqueaderoOcupado(Exception):
    """Una visita sin salida lo está usando: no se puede retirar."""


def parqueaderos(tipo=None, solo_libres=False):
    """Los activos, por código. Cada uno trae `abiertas`: cuántas visitas sin salida lo usan.

    Se cuenta por la relación inversa `visitas`, que crea la FK de `visitantes`, para que esta
    app no importe a esa. Un `filter(visitas__hora_salida__isnull=True)` no serviría: con el
    `LEFT JOIN` también devolvería los que nunca tuvieron visita.
    """
    consulta = Parqueadero.objects.filter(activo=True).annotate(
        abiertas=Count("visitas", filter=Q(visitas__hora_salida__isnull=True))
    )
    if tipo:
        consulta = consulta.filter(tipo=tipo)
    if solo_libres:
        consulta = consulta.filter(abiertas=0)
    return consulta.order_by("codigo")


def crear(actor, codigo, tipo, accesible=False, notas=""):
    """Crea el parqueadero y lo audita. El código repetido (sin distinguir mayúsculas) lo decide la base."""
    try:
        with transaction.atomic():
            parqueadero = Parqueadero.objects.create(
                codigo=codigo, tipo=tipo, accesible=accesible, notas=notas, creado_por=actor
            )
            auditoria.registrar(
                actor,
                "parqueadero.crear",
                "Parqueadero",
                parqueadero.id,
                despues={"codigo": parqueadero.codigo, "tipo": tipo, "accesible": accesible},
            )
    except IntegrityError as error:
        if "parqueadero_codigo_unico" in str(error):
            raise CodigoRepetido() from error
        raise
    return parqueadero


def desactivar(actor, parqueadero_id):
    """Baja lógica. Con una visita sin salida adentro no se retira.

    La fila se bloquea: `visitantes.registrar_ingreso` también la bloquea antes de ocuparla, así que
    no queda un parqueadero retirado con una visita que acaba de entrar.
    """
    with transaction.atomic():
        parqueadero = Parqueadero.objects.select_for_update().filter(pk=parqueadero_id, activo=True).first()
        if parqueadero is None:
            raise ParqueaderoNoEncontrado()
        if parqueadero.visitas.filter(hora_salida__isnull=True).exists():
            raise ParqueaderoOcupado()
        parqueadero.activo = False
        parqueadero.save(update_fields=["activo"])
        auditoria.registrar(
            actor,
            "parqueadero.desactivar",
            "Parqueadero",
            parqueadero.id,
            antes={"activo": True},
            despues={"activo": False, "codigo": parqueadero.codigo},
        )
    return parqueadero
