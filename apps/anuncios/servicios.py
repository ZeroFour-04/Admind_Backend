"""Anuncios con alcance de conjunto o de vivienda (HU-25). No saben nada de HTTP.

Publicar avisa una sola vez, por el canal de notificaciones. Editar solo cambia el texto.
"""
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.anuncios.models import Alcance, Anuncio
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


class UnidadNoEncontrada(Exception):
    """La vivienda no existe en el conjunto activo."""


def publicar(autor, *, titulo, cuerpo, alcance, unidad=None):
    unidad_destino = None
    if alcance == Alcance.VIVIENDA:
        # El manager solo ve las unidades del conjunto activo: una de otro conjunto no aparece.
        unidad_destino = Unidad.objects.filter(pk=unidad).first()
        if unidad_destino is None:
            raise UnidadNoEncontrada()
    with transaction.atomic():
        anuncio = Anuncio.objects.create(
            titulo=titulo, cuerpo=cuerpo, alcance=alcance, unidad=unidad_destino, autor=autor
        )
        notificar(Aviso(titulo, cuerpo, origen="anuncio", referencia=anuncio.id), destinatarios(anuncio))
    return anuncio


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
    anuncios = Anuncio.objects.select_related("unidad", "autor").order_by("-publicado_en")
    if ve_todo_el_tablon(persona, conjunto_id):
        return anuncios
    return anuncios.filter(Q(alcance=Alcance.CONJUNTO) | Q(unidad__in=unidades.unidades_de(persona)))


def puede_editar(persona, permisos, anuncio):
    """Solo quien lo publicó, y mientras conserve el permiso de su alcance."""
    return anuncio.autor_id == persona.id and PERMISO_POR_ALCANCE[anuncio.alcance] in permisos
