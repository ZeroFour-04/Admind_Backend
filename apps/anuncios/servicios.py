"""Anuncios con alcance de conjunto o de vivienda (HU-25). No saben nada de HTTP.

Publicar avisa una sola vez, por el canal de notificaciones. Editar solo cambia el texto.
Las fotos se suben al publicar y no cambian después.
"""
from django.db import transaction
from django.db.models import Prefetch, Q, prefetch_related_objects
from django.utils import timezone

from apps.anuncios.models import Alcance, Anuncio, FotoDeAnuncio
from apps.conjuntos.servicios import tipo_real_de_imagen
from apps.notificaciones.canal import Aviso, notificar
from apps.permisos.models import Asignacion
from apps.permisos.servicios import permisos_efectivos
from apps.unidades import servicios as unidades
from apps.unidades.models import Unidad

# Dos permisos separados en el catálogo: dirigir a una vivienda no viene incluido en publicar.
PERMISO_POR_ALCANCE = {
    Alcance.CONJUNTO: "anuncio.publicar",
    Alcance.VIVIENDA: "anuncio.dirigir",
}


TAMANO_MAXIMO_FOTO = 5 * 1024 * 1024  # bytes


class UnidadNoEncontrada(Exception):
    """La vivienda no existe en el conjunto activo."""


class FotoInvalida(Exception):
    """Un archivo no sirve como foto del anuncio. Trae el mensaje para quien lo subió."""

    def __init__(self, mensaje):
        super().__init__(mensaje)
        self.mensaje = mensaje


def publicar(autor, *, titulo, cuerpo, alcance, unidad=None, fotos=()):
    """`fotos` trae el contenido de cada una, en el orden en que se van a mostrar."""
    unidad_destino = None
    if alcance == Alcance.VIVIENDA:
        # El manager solo ve las unidades del conjunto activo: una de otro conjunto no aparece.
        unidad_destino = Unidad.objects.filter(pk=unidad).first()
        if unidad_destino is None:
            raise UnidadNoEncontrada()
    # Se revisan todas antes de guardar nada: con una foto que no sirve, no se publica ni se avisa.
    tipos = tipos_de_las_fotos(fotos)
    with transaction.atomic():
        anuncio = Anuncio.objects.create(
            titulo=titulo, cuerpo=cuerpo, alcance=alcance, unidad=unidad_destino, autor=autor
        )
        # Una por una y no con bulk_create: así save() le pone el conjunto a cada foto.
        for orden, (contenido, tipo) in enumerate(zip(fotos, tipos)):
            FotoDeAnuncio.objects.create(anuncio=anuncio, contenido=contenido, tipo=tipo, orden=orden)
        aviso = Aviso(titulo, cuerpo_del_aviso(cuerpo, len(fotos)), origen="anuncio", referencia=anuncio.id)
        notificar(aviso, destinatarios(anuncio))
    # Quien lo recibe lee los ids de las fotos: se le cargan sin la imagen, como en el tablón.
    prefetch_related_objects([anuncio], fotos_sin_contenido())
    return anuncio


def tipos_de_las_fotos(fotos):
    """El tipo real de cada foto, en orden. Con la primera que no sirva, FotoInvalida.

    El nombre y el tipo que manda el navegador no cuentan: decide la firma del archivo.
    """
    tipos = []
    for numero, contenido in enumerate(fotos, start=1):
        if not contenido:
            raise FotoInvalida(f"La foto {numero} está vacía.")
        if len(contenido) > TAMANO_MAXIMO_FOTO:
            raise FotoInvalida(f"La foto {numero} pesa más de {TAMANO_MAXIMO_FOTO // (1024 * 1024)} MB.")
        tipo = tipo_real_de_imagen(contenido)
        if tipo is None:
            raise FotoInvalida(f"La foto {numero} no es una imagen PNG, JPG o WebP.")
        tipos.append(tipo)
    return tipos


def cuerpo_del_aviso(cuerpo, cantidad_de_fotos):
    """El texto que llega a la bandeja y al correo. Las fotos no viajan en el aviso: se ven en AdMind."""
    if cantidad_de_fotos == 0:
        return cuerpo
    if cantidad_de_fotos == 1:
        return f"{cuerpo}\n\nEste anuncio tiene 1 foto. Mírala en AdMind."
    return f"{cuerpo}\n\nEste anuncio tiene {cantidad_de_fotos} fotos. Míralas en AdMind."


def fotos_sin_contenido():
    """Las fotos de cada anuncio, en orden y sin la imagen: para listar bastan sus ids.

    Se arma en cada llamada y no como constante del módulo, porque el manager filtra por el
    conjunto activo en el momento en que se le pide la consulta.
    """
    return Prefetch("fotos", queryset=FotoDeAnuncio.objects.defer("contenido").order_by("orden"))


def destinatarios(anuncio):
    """Todo el conjunto: quien tenga una asignación vigente en él. Una vivienda: sus vínculos vigentes."""
    if anuncio.alcance == Alcance.VIVIENDA:
        personas = unidades.destinatarios(anuncio.unidad, unidades.Hecho.ANUNCIO_A_VIVIENDA)
        return list(personas.values_list("pk", flat=True))
    asignaciones = Asignacion.objects.vigentes().filter(conjunto_id=anuncio.conjunto_id)
    return list(asignaciones.values_list("persona_id", flat=True).distinct())


def editar(anuncio, **campos):
    """Cambia el título o el texto. No vuelve a avisar: el aviso salió al publicar."""
    for campo, valor in campos.items():
        setattr(anuncio, campo, valor)
    anuncio.editado_en = timezone.now()
    anuncio.save(update_fields=[*campos, "editado_en"])
    return anuncio


def ve_todo_el_tablon(persona, conjunto_id):
    permisos = permisos_efectivos(persona, conjunto_id)
    return any(permiso in permisos for permiso in PERMISO_POR_ALCANCE.values())


def tablon(persona, conjunto_id):
    """Lo que la persona ve del tablón del conjunto activo.

    Quien publica ve todos los anuncios. Los demás, los de todo el conjunto y los dirigidos a
    las viviendas donde tienen un vínculo vigente: un anuncio dirigido no es para los vecinos.
    """
    anuncios = (
        Anuncio.objects.select_related("unidad", "autor")
        .prefetch_related(fotos_sin_contenido())
        .order_by("-publicado_en")
    )
    if ve_todo_el_tablon(persona, conjunto_id):
        return anuncios
    return anuncios.filter(Q(alcance=Alcance.CONJUNTO) | Q(unidad__in=unidades.unidades_de(persona)))


def foto_visible(persona, conjunto_id, anuncio_id, foto_id):
    """La foto, si su anuncio está en el tablón de la persona; si no, None.

    Quien no ve un anuncio dirigido a otra vivienda tampoco ve sus fotos.
    """
    if not tablon(persona, conjunto_id).filter(pk=anuncio_id).exists():
        return None
    return FotoDeAnuncio.objects.filter(pk=foto_id, anuncio_id=anuncio_id).first()


def puede_editar(persona, permisos, anuncio):
    """Solo quien lo publicó, y mientras conserve el permiso de su alcance."""
    return anuncio.autor_id == persona.id and PERMISO_POR_ALCANCE[anuncio.alcance] in permisos
