"""El pago declarado de una reserva y sus comprobantes (HU-16). No sabe nada de HTTP.

El sistema no verifica el dinero ni lo cobra: declarar un pago es dejar constancia de que una
persona de la administración dijo haberlo recibido. Aprobar una reserva no depende de esto
(`servicios.decidir_solicitud` no se toca) y subir un comprobante no cambia el estado del pago.

El permiso (qué puede hacer el rol) lo revisa la vista; la pertenencia (sobre qué fila) la revisa
este módulo, y responde `SolicitudNoEncontrada` para no decir si la solicitud existe.
"""
from django.db import transaction
from django.utils import timezone

from apps.auditoria import servicios as auditoria
from apps.comun.archivos import comprobantes
from apps.reservas import servicios
from apps.reservas.models import ComprobanteDePago, EstadoSolicitud, Solicitud

# Mientras la solicitud sigue viva y sin decidir en contra, el pago se puede declarar (plan D1 a).
SE_PUEDE_PAGAR = [EstadoSolicitud.APARTADA, EstadoSolicitud.RESERVADA]
MAXIMO_DE_COMPROBANTES = 3
NOMBRE_SIN_NOMBRE = "comprobante"


class PagoNoPermitido(Exception):
    """La solicitud no está apartada ni reservada."""


class PagoYaDeclarado(Exception):
    """El pago de esta solicitud ya tiene una declaración."""


class PagoNoDeclarado(Exception):
    """No hay declaración que retirar."""


class DemasiadosComprobantes(Exception):
    """La solicitud ya tiene el máximo de comprobantes."""


def solicitud_bloqueada(solicitud_id):
    """La fila de la solicitud bloqueada hasta que termine la transacción, o `SolicitudNoEncontrada`."""
    solicitud = Solicitud.objects.select_for_update().filter(pk=solicitud_id).first()
    if solicitud is None:
        raise servicios.SolicitudNoEncontrada()
    return solicitud


def para_gestion(solicitud_id):
    """La solicitud como la ve gestión: con el residente, la decisión, quién declaró y los comprobantes sin contenido."""
    consulta = Solicitud.objects.select_related("area", "persona", "unidad", "decidida_por", "pago_declarado_por")
    return servicios.con_comprobantes(consulta).get(pk=solicitud_id)


def guardar_comprobante(actor, solicitud, nombre, contenido, datos=None):
    """Valida el archivo por su firma, revisa el tope y crea la fila. Lo usan `declarar` y `subir_comprobante`.

    Va dentro de la transacción que ya bloqueó la solicitud: dos subidas a la vez no pasan el tope.
    """
    datos = datos or comprobantes.validar_comprobante(contenido)
    if ComprobanteDePago.objects.filter(solicitud=solicitud).count() >= MAXIMO_DE_COMPROBANTES:
        raise DemasiadosComprobantes()
    return ComprobanteDePago.objects.create(
        solicitud=solicitud,
        contenido=contenido,
        nombre=(nombre or "").strip()[:120] or NOMBRE_SIN_NOMBRE,
        subido_por=actor,
        **datos,
    )


def declarar(actor, solicitud_id, nombre=None, contenido=None):
    """Deja constancia de quién declaró el pago y cuándo; si llega un archivo, lo guarda en la misma transacción.

    Dos administradores que declaran a la vez dejan una sola declaración: la segunda espera el
    bloqueo de la fila, ve el pago ya declarado y recibe `PagoYaDeclarado`.
    """
    # El archivo se revisa antes de bloquear nada: un archivo malo no deja el pago declarado.
    datos = comprobantes.validar_comprobante(contenido) if contenido is not None else None
    with transaction.atomic():
        solicitud = solicitud_bloqueada(solicitud_id)
        if solicitud.estado not in SE_PUEDE_PAGAR:
            raise PagoNoPermitido()
        if solicitud.pago_declarado_por_id is not None:
            raise PagoYaDeclarado()

        ahora = timezone.now()
        solicitud.pago_declarado_por = actor
        solicitud.pago_declarado_en = ahora
        solicitud.save(update_fields=["pago_declarado_por", "pago_declarado_en"])
        despues = {"declarado_por": str(actor.id), "declarado_en": ahora, "estado": solicitud.estado}
        if datos is not None:
            comprobante = guardar_comprobante(actor, solicitud, nombre, contenido, datos)
            despues["comprobante"] = {"id": str(comprobante.id), "tipo": datos["tipo"], "huella": datos["huella"]}
        auditoria.registrar(
            actor,
            "reserva.declarar_pago",
            "Solicitud",
            solicitud.id,
            antes={"pago_declarado": False},
            despues=despues,
        )
    return para_gestion(solicitud_id)


def retirar_declaracion(actor, solicitud_id, motivo):
    """Deshace una declaración hecha por error (plan D6 a). El motivo es obligatorio y queda en la auditoría.

    Los comprobantes no se tocan: son evidencia y la solicitud conserva el máximo.
    """
    motivo = motivo.strip()
    if not motivo:
        raise ValueError("El motivo es obligatorio.")
    with transaction.atomic():
        solicitud = solicitud_bloqueada(solicitud_id)
        if solicitud.pago_declarado_por_id is None:
            raise PagoNoDeclarado()
        antes = {
            "declarado_por": str(solicitud.pago_declarado_por_id),
            "declarado_en": solicitud.pago_declarado_en,
        }
        solicitud.pago_declarado_por = None
        solicitud.pago_declarado_en = None
        solicitud.save(update_fields=["pago_declarado_por", "pago_declarado_en"])
        auditoria.registrar(
            actor,
            "reserva.retirar_pago",
            "Solicitud",
            solicitud.id,
            antes=antes,
            despues={"pago_declarado": False},
            detalle={"motivo": motivo},
        )
    return para_gestion(solicitud_id)


def subir_comprobante(persona, solicitud_id, nombre, contenido):
    """El residente sube un comprobante a una solicitud suya, mientras el pago no esté declarado (P7).

    Sobre la solicitud de otra persona lanza `SolicitudNoEncontrada`: no se dice si existe.
    Subir no declara nada: el estado del pago no cambia.
    """
    datos = comprobantes.validar_comprobante(contenido)
    with transaction.atomic():
        solicitud = solicitud_bloqueada(solicitud_id)
        if solicitud.persona_id != persona.id:
            raise servicios.SolicitudNoEncontrada()
        if solicitud.estado not in SE_PUEDE_PAGAR:
            raise PagoNoPermitido()
        if solicitud.pago_declarado_por_id is not None:
            raise PagoYaDeclarado()

        comprobante = guardar_comprobante(persona, solicitud, nombre, contenido, datos)
        auditoria.registrar(
            persona,
            "reserva.subir_comprobante",
            "Solicitud",
            solicitud.id,
            despues={"comprobante": str(comprobante.id), "tipo": datos["tipo"], "huella": datos["huella"]},
        )
    return servicios.detalle(persona, solicitud_id)


def comprobante_para(persona, puede_gestionar, comprobante_id):
    """El comprobante con su contenido si la persona puede verlo (P8); si no, None.

    Lo ve quien gestiona pagos o aprueba reservas, y la persona que hizo la solicitud.
    """
    comprobante = ComprobanteDePago.objects.select_related("solicitud").filter(pk=comprobante_id).first()
    if comprobante is None:
        return None
    if puede_gestionar or comprobante.solicitud.persona_id == persona.id:
        return comprobante
    return None
