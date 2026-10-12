"""Creación y consulta de casos del conjunto activo."""
from django.db import transaction
from django.db.models import Prefetch

from apps.casos.models import Caso, EstadoCaso, FotoDeCaso, PrioridadCaso
from apps.conjuntos.servicios import tipo_real_de_imagen
from apps.unidades.models import VinculoUnidad

TAMANO_MAXIMO_FOTO = 5 * 1024 * 1024


class CasoNoGestionable(Exception):
    """El caso ya no está pendiente de revisión."""


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
    return caso


def casos_visibles(persona, puede_ver_todos):
    casos = Caso.objects.select_related("autor").order_by("-creado_en")
    if not puede_ver_todos:
        casos = casos.filter(autor=persona)
    return _casos_con_detalles(casos)


def casos_de_todo_el_conjunto():
    casos = Caso.objects.select_related("autor").order_by("-creado_en")
    return _casos_con_detalles(casos)


def _casos_con_detalles(casos):
    fotos = FotoDeCaso.objects.only("id", "caso_id").order_by("id")
    vinculos_residenciales = (
        VinculoUnidad.objects.vigentes()
        .filter(reside=True)
        .select_related("unidad")
        .order_by("unidad__nombre")
    )
    return casos.prefetch_related(
        Prefetch("foto", queryset=fotos, to_attr="foto_cargada"),
        Prefetch("autor__vinculos", queryset=vinculos_residenciales, to_attr="vinculos_residenciales_actuales"),
    )
def casos_redirigidos_a_administracion():
    casos = Caso.objects.filter(estado=EstadoCaso.REDIRIGIDO).select_related("autor").order_by("-creado_en")
    return _casos_con_detalles(casos)


def _caso_pendiente(caso_id):
    caso = Caso.objects.select_for_update().filter(pk=caso_id).first()
    if caso is None:
        return None
    if caso.estado != EstadoCaso.ABIERTO:
        raise CasoNoGestionable
    return caso


def rechazar(caso_id, motivo):
    motivo = motivo.strip()
    if not motivo:
        raise ValueError("Escribe la razón del rechazo.")
    with transaction.atomic():
        caso = _caso_pendiente(caso_id)
        if caso is None:
            return None
        caso.estado = EstadoCaso.RECHAZADO
        caso.motivo_rechazo = motivo
        caso.save(update_fields=["estado", "motivo_rechazo"])
    return caso


def redirigir(caso_id):
    with transaction.atomic():
        caso = _caso_pendiente(caso_id)
        if caso is None:
            return None
        caso.estado = EstadoCaso.REDIRIGIDO
        caso.save(update_fields=["estado"])
    return caso


def foto_visible(persona, caso_id, foto_id, puede_ver_todos):
    consulta = FotoDeCaso.objects.filter(pk=foto_id, caso_id=caso_id).select_related("caso")
    if not puede_ver_todos:
        consulta = consulta.filter(caso__autor=persona)
    return consulta.first()
