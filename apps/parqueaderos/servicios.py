"""Catálogo de parqueaderos del conjunto activo (HU-28) y su asignación a una vivienda (HU-34). No sabe nada de HTTP.

Toda escritura deja registro en la auditoría. Solo se asignan los de residentes: uno de visitantes no
se encuentra (404) porque la operación filtra por tipo, no porque se deniegue. No existe ninguna
operación que quite un puesto por mora ni como sanción: se reasigna a otra vivienda o se libera
(maestro §4.2, §5.6).
"""
from django.db import IntegrityError, transaction
from django.db.models import Count, Prefetch, Q
from django.utils import timezone

from apps.auditoria import servicios as auditoria
from apps.parqueaderos.models import AsignacionParqueadero, Parqueadero, TipoDeParqueadero
from apps.reglas.catalogo import TipoDeRegla
from apps.reglas.models import Regla
from apps.unidades.models import Unidad, VinculoUnidad


class CodigoRepetido(Exception):
    """Ya hay un parqueadero con ese código en el conjunto."""


class ParqueaderoNoEncontrado(Exception):
    """No existe en el conjunto activo, ya estaba retirado o (al asignar) no es de residentes."""


class ParqueaderoOcupado(Exception):
    """Una visita sin salida lo está usando: no se puede retirar."""


class ParqueaderoAsignado(Exception):
    """Está asignado a una vivienda: no se retira hasta liberarlo."""


class UnidadNoEncontrada(Exception):
    """La vivienda no existe en el conjunto activo."""


class YaAsignadoAEsaUnidad(Exception):
    """El puesto ya es de esa vivienda: reasignarlo a ella no cambia nada."""


class SinAsignacionVigente(Exception):
    """El puesto ya estaba libre: no hay nada que liberar."""


class TopeDeVehiculosAlcanzado(Exception):
    """La vivienda ya tiene el máximo de puestos de ese vehículo que fijó el conjunto. Trae el mensaje."""

    def __init__(self, mensaje):
        super().__init__(mensaje)
        self.mensaje = mensaje


def parqueaderos(tipo=None, solo_libres=False):
    """Los activos, por código. Cada uno trae `abiertas`: cuántas visitas sin salida lo usan.

    Se cuenta por la relación inversa `visitas`, que crea la FK de `visitantes`, para que esta
    app no importe a esa. Un `filter(visitas__hora_salida__isnull=True)` no serviría: con el
    `LEFT JOIN` también devolvería los que nunca tuvieron visita.

    `asignacion_vigente` (en una lista de cero o una) se trae aparte, con otra consulta: unirla en la
    misma multiplicaría las filas que cuenta `abiertas`.
    """
    consulta = (
        Parqueadero.objects.filter(activo=True)
        .annotate(abiertas=Count("visitas", filter=Q(visitas__hora_salida__isnull=True)))
        .prefetch_related(
            Prefetch(
                "asignaciones",
                queryset=AsignacionParqueadero.objects.filter(vigencia_hasta__isnull=True).select_related("unidad"),
                to_attr="asignacion_vigente",
            )
        )
    )
    if tipo:
        consulta = consulta.filter(tipo=tipo)
    if solo_libres:
        consulta = consulta.filter(abiertas=0)
    return consulta.order_by("codigo")


def crear(actor, codigo, tipo, accesible=False, notas="", vehiculo="carro"):
    """Crea el parqueadero y lo audita. El código repetido (sin distinguir mayúsculas) lo decide la base."""
    try:
        with transaction.atomic():
            parqueadero = Parqueadero.objects.create(
                codigo=codigo, tipo=tipo, vehiculo=vehiculo, accesible=accesible, notas=notas, creado_por=actor
            )
            auditoria.registrar(
                actor,
                "parqueadero.crear",
                "Parqueadero",
                parqueadero.id,
                despues={"codigo": parqueadero.codigo, "tipo": tipo, "vehiculo": vehiculo, "accesible": accesible},
            )
    except IntegrityError as error:
        if "parqueadero_codigo_unico" in str(error):
            raise CodigoRepetido() from error
        raise
    return parqueadero


def desactivar(actor, parqueadero_id):
    """Baja lógica. Con una visita sin salida adentro, o asignado a una vivienda, no se retira.

    La fila se bloquea: `visitantes.registrar_ingreso` y `asignar` también la bloquean antes de usarla,
    así que no queda un parqueadero retirado con una visita que acaba de entrar ni con una asignación nueva.
    """
    with transaction.atomic():
        parqueadero = Parqueadero.objects.select_for_update().filter(pk=parqueadero_id, activo=True).first()
        if parqueadero is None:
            raise ParqueaderoNoEncontrado()
        if parqueadero.visitas.filter(hora_salida__isnull=True).exists():
            raise ParqueaderoOcupado()
        if parqueadero.asignaciones.filter(vigencia_hasta__isnull=True).exists():
            raise ParqueaderoAsignado()
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


# Asignación de los parqueaderos de residentes (HU-34)


def tope_por_vivienda():
    """`{carro, moto, bicicleta}` de la regla PARQUEADEROS_POR_VIVIENDA vigente hoy, o `None` si no está definida.

    Sin regla no hay tope (D6 a). Se lee como `pagos.mora` lee el día límite: de la tabla, sin pasar por la API.
    """
    regla = (
        Regla.objects.vigentes()
        .filter(tipo=TipoDeRegla.PARQUEADEROS_POR_VIVIENDA, area__isnull=True)
        .order_by("-vigencia_desde", "-creada_en")
        .first()
    )
    return regla.parametros if regla else None


def vigentes_de_la_vivienda(unidad):
    return AsignacionParqueadero.objects.filter(unidad=unidad, vigencia_hasta__isnull=True)


def comprobar_tope(unidad, parqueadero):
    """Si la vivienda ya tiene el máximo de puestos de ese vehículo, `TopeDeVehiculosAlcanzado`."""
    tope = tope_por_vivienda()
    if tope is None:
        return
    maximo = tope[parqueadero.vehiculo]
    tiene = vigentes_de_la_vivienda(unidad).filter(parqueadero__vehiculo=parqueadero.vehiculo).count()
    if tiene >= maximo:
        nombre = parqueadero.get_vehiculo_display().lower()
        raise TopeDeVehiculosAlcanzado(
            f"Esta vivienda ya tiene el máximo de parqueaderos de {nombre} que fijó el conjunto ({maximo})."
            if maximo
            else f"El conjunto no asigna parqueaderos de {nombre} a las viviendas."
        )


def datos_de_la_asignacion(asignacion):
    return {
        "parqueadero": asignacion.parqueadero.codigo,
        "unidad": asignacion.unidad.nombre,
        "vigencia_desde": asignacion.vigencia_desde,
        "vigencia_hasta": asignacion.vigencia_hasta,
    }


def asignar(actor, parqueadero_id, unidad_id):
    """Asigna el puesto a la vivienda; si ya era de otra, la reasigna cerrando la anterior hoy (P4).

    Devuelve `(asignacion, reasignada)`. Se bloquea el puesto y luego la vivienda, en ese orden: sin el
    segundo bloqueo, diez asignaciones a la vez a una misma vivienda se saltarían el tope. El índice
    único parcial sigue siendo la última palabra sobre «un puesto, una asignación vigente».
    """
    with transaction.atomic():
        parqueadero = (
            Parqueadero.objects.select_for_update()
            .filter(pk=parqueadero_id, tipo=TipoDeParqueadero.RESIDENTES, activo=True)
            .first()
        )
        if parqueadero is None:
            raise ParqueaderoNoEncontrado()
        unidad = Unidad.objects.select_for_update().filter(pk=unidad_id).first()
        if unidad is None:
            raise UnidadNoEncontrada()
        anterior = parqueadero.asignaciones.filter(vigencia_hasta__isnull=True).select_related("unidad").first()
        if anterior is not None and anterior.unidad_id == unidad.id:
            raise YaAsignadoAEsaUnidad()
        # Reasignar cuenta solo a la vivienda que recibe: la que cede no cambia su tope.
        comprobar_tope(unidad, parqueadero)
        hoy = timezone.localdate()
        if anterior is not None:
            anterior.vigencia_hasta = hoy
            anterior.cerrado_por = actor
            anterior.save(update_fields=["vigencia_hasta", "cerrado_por"])
        asignacion = AsignacionParqueadero.objects.create(
            parqueadero=parqueadero, unidad=unidad, vigencia_desde=hoy, registrado_por=actor
        )
        auditoria.registrar(
            actor,
            "parqueadero.reasignar" if anterior else "parqueadero.asignar",
            "Parqueadero",
            parqueadero.id,
            antes=datos_de_la_asignacion(anterior) if anterior else None,
            despues=datos_de_la_asignacion(asignacion),
        )
    return asignacion, anterior is not None


def liberar(actor, parqueadero_id):
    """Cierra la asignación vigente hoy y deja el puesto sin asignar. No borra nada: queda en el historial."""
    with transaction.atomic():
        parqueadero = (
            Parqueadero.objects.select_for_update()
            .filter(pk=parqueadero_id, tipo=TipoDeParqueadero.RESIDENTES, activo=True)
            .first()
        )
        if parqueadero is None:
            raise ParqueaderoNoEncontrado()
        vigente = parqueadero.asignaciones.filter(vigencia_hasta__isnull=True).select_related("unidad").first()
        if vigente is None:
            raise SinAsignacionVigente()
        antes = datos_de_la_asignacion(vigente)
        vigente.vigencia_hasta = timezone.localdate()
        vigente.cerrado_por = actor
        vigente.save(update_fields=["vigencia_hasta", "cerrado_por"])
        auditoria.registrar(
            actor, "parqueadero.liberar", "Parqueadero", parqueadero.id, antes=antes,
            despues=datos_de_la_asignacion(vigente),
        )
    return vigente


def historial(parqueadero_id):
    """Todas las asignaciones del puesto, la más reciente primero. Sirve también si ya está retirado."""
    parqueadero = Parqueadero.objects.filter(pk=parqueadero_id, tipo=TipoDeParqueadero.RESIDENTES).first()
    if parqueadero is None:
        raise ParqueaderoNoEncontrado()
    asignaciones = parqueadero.asignaciones.select_related("unidad", "registrado_por", "cerrado_por").order_by(
        "-vigencia_desde", "-registrado_en"
    )
    return parqueadero, asignaciones


def mios(persona):
    """Los puestos vigentes de las viviendas donde la persona tiene un vínculo vigente, por código.

    No pide permiso: cada persona ve los de sus propias viviendas, como la bandeja de notificaciones.
    """
    unidades = VinculoUnidad.objects.vigentes().filter(persona=persona).values("unidad_id")
    return (
        AsignacionParqueadero.objects.filter(vigencia_hasta__isnull=True, unidad_id__in=unidades)
        .select_related("parqueadero", "unidad")
        .order_by("parqueadero__codigo")
    )
