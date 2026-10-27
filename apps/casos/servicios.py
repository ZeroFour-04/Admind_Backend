"""Los casos del conjunto activo (HU-29). No sabe nada de HTTP.

Un caso es una máquina de estados: cada operación dice de qué estados sale y a cuál llega, y todo lo
demás es `CasoNoGestionable`. La Secretaría clasifica (toma, prioriza, descarta, redirige) y la
Administración decide (responde o rechaza). Administración puede atender un caso sin que nadie lo
redirija: el sistema tiene que funcionar con cero secretarías.
"""
from django.db import transaction
from django.db.models import Case, IntegerField, Prefetch, Value, When
from django.utils import timezone

from apps.auditoria import servicios as auditoria
from apps.casos.models import (
    ABIERTOS,
    EN_SECRETARIA,
    Caso,
    CausalDeDescarte,
    EstadoCaso,
    FotoDeCaso,
    PrioridadCaso,
)
from apps.conjuntos.servicios import tipo_real_de_imagen
from apps.notificaciones.canal import Aviso, notificar
from apps.personas.servicios import por_nombre
from apps.unidades.models import VinculoUnidad

TAMANO_MAXIMO_FOTO = 5 * 1024 * 1024

# De la más alta a la más baja. La prioridad es texto en la base, así que el orden se dice aquí.
ORDEN_DE_PRIORIDAD = [PrioridadCaso.URGENTE, PrioridadCaso.ALTA, PrioridadCaso.NORMAL, PrioridadCaso.BAJA]

TITULO_DEL_AVISO = {
    EstadoCaso.EN_REVISION: "Tu caso está en revisión",
    EstadoCaso.REDIRIGIDO: "Tu caso pasó a la administración",
    EstadoCaso.RESUELTO: "Tu caso fue resuelto",
    EstadoCaso.RECHAZADO: "Tu caso fue rechazado",
}


class CasoNoEncontrado(Exception):
    """No existe en el conjunto activo."""


class CasoNoGestionable(Exception):
    """El estado actual del caso no permite esa operación."""


class FotoInvalida(Exception):
    """La imagen no tiene un formato admitido o excede el tamaño máximo."""

    def __init__(self, mensaje):
        super().__init__(mensaje)
        self.mensaje = mensaje


def crear(actor, titulo, cuerpo, foto=None):
    tipo = None
    if foto is not None:
        if not foto:
            raise FotoInvalida("La imagen está vacía.")
        if len(foto) > TAMANO_MAXIMO_FOTO:
            raise FotoInvalida("La imagen pesa más de 5 MB.")
        tipo = tipo_real_de_imagen(foto)
        if tipo is None:
            raise FotoInvalida("El archivo no es una imagen PNG, JPG o WebP.")

    with transaction.atomic():
        caso = Caso.objects.create(
            titulo=titulo,
            cuerpo=cuerpo,
            autor=actor,
            prioridad=PrioridadCaso.NORMAL,
        )
        if foto is not None:
            caso.foto_cargada = FotoDeCaso.objects.create(caso=caso, contenido=foto, tipo=tipo)
        auditoria.registrar(actor, "caso.crear", "Caso", caso.id, despues={"estado": caso.estado})
    return caso


def casos_de(persona):
    """Los propios, el más reciente primero."""
    return _casos_con_detalles(Caso.objects.filter(autor=persona).order_by("-creado_en"))


def casos_para_bandeja(
    ver="todos",
    orden="prioridad",
    solo_redirigidos=False,
    estado=None,
    prioridad=None,
    desde=None,
    hasta=None,
    solicitante="",
):
    """Todos los del conjunto, para gestión: primero los abiertos, por prioridad y luego antigüedad.

    `orden="antiguedad"` ignora la prioridad por completo: es la salida de emergencia si algo quedó
    enterrado. El orden no es configurable más allá de eso. Los filtros (HU-22) reducen las filas y
    nunca cambian el orden. `desde` y `hasta` son fechas de creación, inclusive, en la hora local.
    """
    casos = Caso.objects.all()
    if solo_redirigidos:
        casos = casos.filter(estado=EstadoCaso.REDIRIGIDO)
    elif ver == "abiertos":
        casos = casos.filter(estado__in=ABIERTOS)
    if estado:
        casos = casos.filter(estado=estado)
    if prioridad:
        casos = casos.filter(prioridad=prioridad)
    if desde:
        casos = casos.filter(creado_en__date__gte=desde)
    if hasta:
        casos = casos.filter(creado_en__date__lte=hasta)
    if solicitante:
        casos = por_nombre(casos, solicitante, "autor")
    cerrado = Case(When(estado__in=ABIERTOS, then=Value(0)), default=Value(1), output_field=IntegerField())
    criterios = ["cerrado"]
    if orden != "antiguedad":
        peso = Case(
            *[When(prioridad=prioridad, then=Value(puesto)) for puesto, prioridad in enumerate(ORDEN_DE_PRIORIDAD)],
            default=Value(len(ORDEN_DE_PRIORIDAD)),
            output_field=IntegerField(),
        )
        casos = casos.annotate(peso=peso)
        criterios.append("peso")
    return _casos_con_detalles(casos.annotate(cerrado=cerrado).order_by(*criterios, "creado_en"))


def detalle(caso_id, persona=None):
    """Un caso del conjunto. Con `persona`, solo si es suyo: el de otro no existe para ella."""
    casos = Caso.objects.filter(pk=caso_id)
    if persona is not None:
        casos = casos.filter(autor=persona)
    return _casos_con_detalles(casos).first()


def _casos_con_detalles(casos):
    fotos = FotoDeCaso.objects.only("id", "caso_id").order_by("id")
    vinculos_residenciales = (
        VinculoUnidad.objects.vigentes()
        .filter(reside=True)
        .select_related("unidad")
        .order_by("unidad__nombre")
    )
    return casos.select_related("autor", "cerrado_por").prefetch_related(
        Prefetch("foto", queryset=fotos, to_attr="foto_cargada"),
        Prefetch("autor__vinculos", queryset=vinculos_residenciales, to_attr="vinculos_residenciales_actuales"),
    )


def _pasar(actor, caso_id, *, desde, hacia, accion, **campos):
    """Toda transición pasa por aquí: bloquea la fila, revisa el estado, escribe, audita y avisa.

    Con la fila bloqueada, dos personas que actúan a la vez sobre el mismo caso no se pisan: la
    segunda encuentra un estado que ya no le sirve y recibe `CasoNoGestionable`.
    """
    with transaction.atomic():
        caso = Caso.objects.select_for_update(of=("self",)).filter(pk=caso_id).first()
        if caso is None:
            raise CasoNoEncontrado()
        if caso.estado not in desde:
            raise CasoNoGestionable()
        anterior = caso.estado
        caso.estado = hacia
        for campo, valor in campos.items():
            setattr(caso, campo, valor)
        cambiados = ["estado", *campos]
        if hacia not in ABIERTOS:
            caso.cerrado_por = actor
            caso.cerrado_en = timezone.now()
            cambiados += ["cerrado_por", "cerrado_en"]
        caso.save(update_fields=cambiados)
        auditoria.registrar(
            actor, accion, "Caso", caso.id, antes={"estado": anterior}, despues={"estado": hacia, **campos}
        )
        avisar(caso)
    return detalle(caso.id)


def avisar(caso):
    """A quien abrió el caso, por la aplicación y por correo. No dice quién actuó ni trae la nota interna."""
    cuerpo = f"«{caso.titulo}»."
    if caso.estado == EstadoCaso.RESUELTO:
        cuerpo = f"{cuerpo} Respuesta: {caso.respuesta}"
    elif caso.estado == EstadoCaso.RECHAZADO:
        causal = f"{caso.get_causal_rechazo_display()}. " if caso.causal_rechazo else ""
        cuerpo = f"{cuerpo} Motivo: {causal}{caso.motivo_rechazo}"
    aviso = Aviso(TITULO_DEL_AVISO[caso.estado], cuerpo, origen=f"caso.{caso.estado.lower()}", referencia=caso.id)
    notificar(aviso, [caso.autor_id])


def tomar(actor, caso_id):
    """Alguien de gestión lo está viendo. Es opcional: se puede redirigir o cerrar sin pasar por aquí."""
    return _pasar(actor, caso_id, desde=[EstadoCaso.ABIERTO], hacia=EstadoCaso.EN_REVISION, accion="caso.tomar")


def redirigir(actor, caso_id, nota=""):
    """La Secretaría se lo pasa al administrador, con una nota interna si quiere."""
    return _pasar(
        actor,
        caso_id,
        desde=EN_SECRETARIA,
        hacia=EstadoCaso.REDIRIGIDO,
        accion="caso.redirigir",
        nota_redireccion=nota.strip(),
    )


def descartar(actor, caso_id, causal, comentario):
    """La Secretaría lo cierra por causal formal. El comentario lo lee el residente y cuenta como la respuesta."""
    comentario = comentario.strip()
    if causal not in CausalDeDescarte.values:
        raise ValueError("El descarte lleva una causal de la lista.")
    if not comentario:
        raise ValueError("Escribe la razón del rechazo.")
    return _pasar(
        actor,
        caso_id,
        desde=EN_SECRETARIA,
        hacia=EstadoCaso.RECHAZADO,
        accion="caso.descartar",
        causal_rechazo=causal,
        motivo_rechazo=comentario,
    )


def responder(actor, caso_id, respuesta):
    """Administración resuelve solo casos que la Secretaría ya redirigió."""
    respuesta = respuesta.strip()
    if not respuesta:
        raise ValueError("Escribe la respuesta para el residente.")
    return _pasar(
        actor,
        caso_id,
        desde=[EstadoCaso.REDIRIGIDO],
        hacia=EstadoCaso.RESUELTO,
        accion="caso.responder",
        respuesta=respuesta,
    )


def rechazar(actor, caso_id, motivo):
    """Administración rechaza solo casos que la Secretaría ya redirigió."""
    motivo = motivo.strip()
    if not motivo:
        raise ValueError("Escribe la razón del rechazo.")
    return _pasar(
        actor,
        caso_id,
        desde=[EstadoCaso.REDIRIGIDO],
        hacia=EstadoCaso.RECHAZADO,
        accion="caso.rechazar",
        motivo_rechazo=motivo,
    )


def priorizar(actor, caso_id, prioridad, justificacion=""):
    """Cambia la prioridad de un caso abierto. Queda en auditoría con el valor anterior y el nuevo.

    No cambia el estado ni avisa al residente: la prioridad es conveniencia de gestión.
    """
    justificacion = justificacion.strip()
    if prioridad not in PrioridadCaso.values:
        raise ValueError("Esa prioridad no existe.")
    if prioridad == PrioridadCaso.URGENTE and not justificacion:
        raise ValueError("La prioridad urgente lleva una justificación escrita.")
    with transaction.atomic():
        caso = Caso.objects.select_for_update(of=("self",)).filter(pk=caso_id).first()
        if caso is None:
            raise CasoNoEncontrado()
        if caso.estado not in ABIERTOS:
            raise CasoNoGestionable()
        antes = {"prioridad": caso.prioridad}
        caso.prioridad = prioridad
        caso.justificacion_prioridad = justificacion if prioridad == PrioridadCaso.URGENTE else ""
        caso.save(update_fields=["prioridad", "justificacion_prioridad"])
        despues = {"prioridad": prioridad, "justificacion": caso.justificacion_prioridad}
        auditoria.registrar(actor, "caso.priorizar", "Caso", caso.id, antes=antes, despues=despues)
    return detalle(caso.id)


def foto_visible(persona, caso_id, foto_id, puede_ver_todos):
    consulta = FotoDeCaso.objects.filter(pk=foto_id, caso_id=caso_id).select_related("caso")
    if not puede_ver_todos:
        consulta = consulta.filter(caso__autor=persona)
    return consulta.first()
