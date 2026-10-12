"""Registro y salida de visitantes del conjunto activo (HU-27, HU-28). No sabe nada de HTTP.

«Solo Vigilancia registra» es regla de este módulo y no de la vista: así la cumple cualquier
entrada que llegue a él. El parqueadero de visitantes es un recurso limitado (R1): no se pregunta
si está libre antes de escribir; se escribe, y el índice único parcial acepta a una sola visita.
"""
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.auditoria import servicios as auditoria
from apps.comun.bloqueo import bloqueo
from apps.parqueaderos.models import Parqueadero, TipoDeParqueadero
from apps.permisos.catalogo import Rol
from apps.permisos.models import Asignacion
from apps.unidades.models import Unidad
from apps.visitantes.models import Visitante

RESTRICCION_DE_PARQUEADERO = "visitante_parqueadero_ocupado_unico"


class SoloVigilancia(Exception):
    """Quien actúa no tiene el rol Vigilancia vigente en el conjunto."""


class UnidadNoEncontrada(Exception):
    """El apartamento visitado no existe en el conjunto activo."""


class VisitanteNoEncontrado(Exception):
    """No existe en el conjunto activo."""


class YaSalio(Exception):
    """La visita ya tiene su salida registrada."""


class ParqueaderoNoDisponible(Exception):
    """No existe, está retirado o no es de visitantes."""


class ParqueaderoOcupado(Exception):
    """Otra visita lo tomó antes: lo decidió la base."""


def exigir_vigilancia(actor, conjunto_id):
    """La regla de Camilo, ahora aquí: solo el rol Vigilancia registra ingresos y salidas (plan P11)."""
    es_vigilancia = Asignacion.objects.vigentes().filter(
        persona=actor, conjunto_id=conjunto_id, rol=Rol.VIGILANCIA
    ).exists()
    if not es_vigilancia:
        raise SoloVigilancia()


def visitantes_para(solo_de_hoy, buscar=None):
    """El listado, el más reciente primero.

    Para quien solo registra: las de hoy **y** las que siguen adentro de días anteriores. Sin
    eso, una visita que entró ayer y sigue en portería no tendría dónde darle salida (plan P10).
    """
    visitantes = Visitante.objects.select_related("unidad", "parqueadero").order_by("-hora_entrada")
    if solo_de_hoy:
        visitantes = visitantes.filter(
            Q(hora_entrada__date=timezone.localdate()) | Q(hora_salida__isnull=True)
        )
    if buscar:
        termino = buscar.strip()
        if termino:
            visitantes = visitantes.filter(Q(nombre__icontains=termino) | Q(cedula__icontains=termino))
    return visitantes


def registrar_ingreso(
    actor, conjunto_id, *, nombre, cedula, placa_vehiculo, tipo_vehiculo, unidad_id, parqueadero_id=None
):
    """Crea la visita, con su parqueadero si trae, y audita `visitante.registrar`. Todo en una transacción.

    Con `parqueadero_id` se bloquea la fila del parqueadero antes de ocuparlo: así `desactivar` no
    lo retira justo cuando una visita entra. Si otra visita lo ocupó antes, `ParqueaderoOcupado` y
    no queda ninguna fila (plan P6).
    """
    exigir_vigilancia(actor, conjunto_id)
    unidad = Unidad.objects.filter(pk=unidad_id).first()
    if unidad is None:
        raise UnidadNoEncontrada()
    with transaction.atomic():
        parqueadero = None
        if parqueadero_id is not None:
            parqueadero = (
                Parqueadero.objects.select_for_update()
                .filter(pk=parqueadero_id, activo=True, tipo=TipoDeParqueadero.VISITANTES)
                .first()
            )
            if parqueadero is None:
                raise ParqueaderoNoDisponible()

        def crear():
            visitante = Visitante.objects.create(
                nombre=nombre,
                cedula=cedula,
                placa_vehiculo=placa_vehiculo,
                tipo_vehiculo=tipo_vehiculo,
                unidad=unidad,
                parqueadero=parqueadero,
            )
            # Sin nombre ni cédula: la auditoría dice quién y qué, no a quién visitó con sus datos.
            auditoria.registrar(
                actor,
                "visitante.registrar",
                "Visitante",
                visitante.id,
                despues={
                    "unidad": unidad.id,
                    "con_vehiculo": bool(placa_vehiculo),
                    "parqueadero": parqueadero.codigo if parqueadero else None,
                },
            )
            return visitante

        try:
            return bloqueo.tomar(crear)
        except bloqueo.RecursoOcupado as ocupado:
            if ocupado.restriccion == RESTRICCION_DE_PARQUEADERO:
                raise ParqueaderoOcupado() from ocupado
            raise


def registrar_salida(actor, conjunto_id, visitante_id):
    """Pone la hora de salida y quién la registró; si tenía parqueadero, queda libre al instante.

    `select_for_update` evita que dos salidas a la vez se pisen: la segunda espera, ve la hora
    puesta y recibe `YaSalio`.
    """
    exigir_vigilancia(actor, conjunto_id)
    with transaction.atomic():
        visitante = (
            Visitante.objects.select_for_update(of=("self",))
            .select_related("unidad", "parqueadero")
            .filter(pk=visitante_id)
            .first()
        )
        if visitante is None:
            raise VisitanteNoEncontrado()
        if visitante.hora_salida is not None:
            raise YaSalio()
        visitante.hora_salida = timezone.now()
        visitante.salida_registrada_por = actor
        visitante.save(update_fields=["hora_salida", "salida_registrada_por"])
        auditoria.registrar(
            actor,
            "visitante.salida",
            "Visitante",
            visitante.id,
            antes={"hora_salida": None},
            despues={
                "hora_salida": visitante.hora_salida,
                "parqueadero_liberado": visitante.parqueadero.codigo if visitante.parqueadero else None,
            },
        )
    return visitante
