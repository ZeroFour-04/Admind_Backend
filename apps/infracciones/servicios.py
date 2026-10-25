"""Registro de infracciones del conjunto activo (HU-30). No sabe nada de HTTP.

El sistema no sanciona: registra un hecho, lo comunica a propietario y arrendatario de la vivienda y deja
constancia de cómo terminó. Registrar y comunicar pasan en una misma transacción: o pasan las dos o ninguna
(D2 a). Toda escritura deja registro en la auditoría. Aquí no existe ninguna operación que imponga una
sanción, una multa o una restricción de uso (legal §4.2).
"""
from django.db import transaction
from django.db.models import Case, IntegerField, Value, When
from django.utils import timezone

from apps.auditoria import servicios as auditoria
from apps.casos.models import Caso
from apps.infracciones.models import RegistroDeInfraccion
from apps.notificaciones.canal import Aviso, notificar
from apps.unidades.models import Unidad
from apps.unidades.servicios import Hecho, destinatarios

# Riesgo R11: un registro puede leerse como prueba de debido proceso sin serlo. Va en cada aviso.
FRASE_DE_R11 = (
    "Este registro deja constancia de la comunicación. No es una sanción ni reemplaza el procedimiento "
    "del art. 59 de la Ley 675."
)
ORIGEN_DEL_REGISTRO = "infraccion"
ORIGEN_DEL_CIERRE = "infraccion.cierre"


class InfraccionNoEncontrada(Exception):
    """No existe en el conjunto activo."""


class UnidadNoEncontrada(Exception):
    """La vivienda no existe en el conjunto activo."""


class CasoNoEncontrado(Exception):
    """El caso de donde nace no existe en el conjunto activo."""


class SinDestinatarios(Exception):
    """La vivienda no tiene propietario ni arrendatario vigentes: sin comunicación no hay registro."""


class YaCerrada(Exception):
    """El registro ya se cerró: la fecha y el comentario del cierre no se cambian."""


class YaAnulada(Exception):
    """El registro ya está anulado."""


def registros():
    """Todos los del conjunto: primero los abiertos, y luego el más reciente primero. Los anulados siguen en la lista."""
    abierto = Case(
        When(cierre_fecha__isnull=True, anulado=False, then=Value(0)), default=Value(1), output_field=IntegerField()
    )
    return (
        RegistroDeInfraccion.objects.select_related("unidad", "registrado_por", "cerrado_por", "anulado_por")
        .annotate(orden=abierto)
        .order_by("orden", "-registrado_en")
    )


def detalle(registro_id):
    return registros().filter(pk=registro_id).first()


def datos_del_registro(registro):
    """Lo que queda en la auditoría: nunca la descripción del hecho entera, que es del propio registro."""
    return {
        "unidad": registro.unidad.nombre,
        "fecha_hecho": registro.fecha_hecho,
        "cierre_fecha": registro.cierre_fecha,
        "anulado": registro.anulado,
    }


def _fecha(fecha):
    return fecha.strftime("%d/%m/%Y")


def registrar(actor, unidad_id, descripcion_hecho, fecha_hecho, caso_id=None):
    """Registra la infracción y la comunica, en la misma transacción.

    La comunicación va a todos los vínculos vigentes de la vivienda, propietario y arrendatario, residan o no
    (C-318/02). Sin ninguno, no se registra: `SinDestinatarios`. El aviso no dice quién registró.
    """
    with transaction.atomic():
        unidad = Unidad.objects.filter(pk=unidad_id).first()
        if unidad is None:
            raise UnidadNoEncontrada()
        caso = None
        if caso_id is not None:
            caso = Caso.objects.filter(pk=caso_id).first()
            if caso is None:
                raise CasoNoEncontrado()
        personas = list(destinatarios(unidad, Hecho.INFRACCION).values_list("pk", flat=True))
        if not personas:
            raise SinDestinatarios()
        registro = RegistroDeInfraccion.objects.create(
            unidad=unidad,
            caso=caso,
            descripcion_hecho=descripcion_hecho,
            fecha_hecho=fecha_hecho,
            registrado_por=actor,
            fecha_notificacion=timezone.now(),
        )
        cuerpo = (
            f"Se registró un hecho ocurrido el {_fecha(fecha_hecho)} en {unidad.nombre}: {descripcion_hecho}\n\n"
            f"{FRASE_DE_R11}"
        )
        notificar(Aviso("Registro de infracción", cuerpo, ORIGEN_DEL_REGISTRO, registro.id), personas)
        auditoria.registrar(
            actor,
            "infraccion.registrar",
            "RegistroDeInfraccion",
            registro.id,
            despues={**datos_del_registro(registro), "caso": str(caso.id) if caso else None},
        )
    return detalle(registro.id)


def cerrar(actor, registro_id, comentario):
    """Cierra con fecha y comentario. No toca el hecho ni la fecha de notificación. Avisa a la vivienda (D5 a)."""
    with transaction.atomic():
        registro = RegistroDeInfraccion.objects.select_for_update().filter(pk=registro_id).first()
        if registro is None:
            raise InfraccionNoEncontrada()
        if registro.anulado:
            raise YaAnulada()
        if registro.cierre_fecha is not None:
            raise YaCerrada()
        antes = datos_del_registro(registro)
        registro.cierre_fecha = timezone.now()
        registro.cierre_comentario = comentario
        registro.cerrado_por = actor
        registro.save(update_fields=["cierre_fecha", "cierre_comentario", "cerrado_por"])
        personas = list(destinatarios(registro.unidad, Hecho.INFRACCION).values_list("pk", flat=True))
        cuerpo = (
            f"Se cerró el registro del hecho del {_fecha(registro.fecha_hecho)} en {registro.unidad.nombre}. "
            f"Comentario: {comentario}\n\n{FRASE_DE_R11}"
        )
        notificar(Aviso("Cierre del registro de infracción", cuerpo, ORIGEN_DEL_CIERRE, registro.id), personas)
        auditoria.registrar(
            actor, "infraccion.cerrar", "RegistroDeInfraccion", registro.id,
            antes=antes, despues=datos_del_registro(registro),
        )
    return detalle(registro.id)


def anular(actor, registro_id, motivo):
    """Anula un registro equivocado: sigue en la lista, tachado y con su motivo. No avisa a la vivienda (D5 a)."""
    with transaction.atomic():
        registro = RegistroDeInfraccion.objects.select_for_update().filter(pk=registro_id).first()
        if registro is None:
            raise InfraccionNoEncontrada()
        if registro.anulado:
            raise YaAnulada()
        antes = datos_del_registro(registro)
        registro.anulado = True
        registro.anulacion_motivo = motivo
        registro.anulado_por = actor
        registro.anulado_en = timezone.now()
        registro.save(update_fields=["anulado", "anulacion_motivo", "anulado_por", "anulado_en"])
        auditoria.registrar(
            actor, "infraccion.anular", "RegistroDeInfraccion", registro.id,
            antes=antes, despues={**datos_del_registro(registro), "motivo": motivo},
        )
    return detalle(registro.id)
