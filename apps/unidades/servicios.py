"""Unidades del conjunto activo y enrutamiento por vínculos (maestro §5.5). No saben nada de HTTP.

El enrutamiento decide **a quién** le llega un hecho sobre una unidad. **Por dónde** le llega
lo decide el canal de `apps/notificaciones/`.
"""
from enum import Enum

from django.db import IntegrityError, transaction
from django.db.models import Count, F, Max, Q
from django.db.models.functions import Length
from django.utils import timezone

from apps.auditoria import servicios as auditoria
from apps.comun.aislamiento.contexto import conjunto_activo_id
from apps.permisos.models import Asignacion
from apps.personas.models import Persona
from apps.unidades import estructura
from apps.unidades.models import Agrupacion, TipoVinculo, Unidad, VinculoUnidad


class Hecho(Enum):
    ANUNCIO_A_VIVIENDA = "anuncio_a_vivienda"
    OPERATIVO = "operativo"
    ASAMBLEA = "asamblea"
    INFRACCION = "infraccion"
    MORA = "mora"


# Qué vínculos vigentes de la unidad reciben cada hecho. Es una consulta, no un IF sobre roles.
VINCULOS_POR_HECHO = {
    # Propietario y arrendatario, residan o no (maestro §5.7, HU-25).
    Hecho.ANUNCIO_A_VIVIENDA: Q(),
    # Reserva, anuncio operativo, visitante en portería: quien vive ahí.
    Hecho.OPERATIVO: Q(reside=True),
    # Convocatoria y acta de asamblea: el propietario, aunque no resida (art. 39).
    Hecho.ASAMBLEA: Q(tipo=TipoVinculo.PROPIETARIO),
    # Comunicación de infracción: propietario y arrendatario, ambos (C-318/02).
    Hecho.INFRACCION: Q(),
    # Mora y paz y salvo: el propietario, que es el obligado.
    Hecho.MORA: Q(tipo=TipoVinculo.PROPIETARIO),
}


class NombreRepetido(Exception):
    """Ya hay una unidad con ese nombre en el conjunto."""


class AgrupacionDeOtroTipo(Exception):
    """Ya hay una agrupación con ese nombre y guarda otro tipo de vivienda."""

    def __init__(self, nombre):
        super().__init__(nombre)
        self.nombre = nombre


class EstructuraCambiada(Exception):
    """Alguien registró esas mismas viviendas mientras se generaban."""


class PersonaSinAsignacion(Exception):
    """La persona no tiene un rol vigente en el conjunto activo (plan P3). Primero se vincula (HU-07)."""


class VinculoDuplicado(Exception):
    """La persona ya tiene un vínculo vigente de ese tipo sobre la unidad."""


class VinculoYaCerrado(Exception):
    """El vínculo ya tenía fecha de cierre."""


class CierreAntesDelInicio(Exception):
    """La fecha de cierre es anterior al inicio del vínculo."""


def unidades_del_conjunto():
    """Las unidades con cuántos vínculos vigentes tiene cada una."""
    hoy = timezone.localdate()
    vigente = Q(vinculos__vigencia_desde__lte=hoy) & (
        Q(vinculos__vigencia_hasta__isnull=True) | Q(vinculos__vigencia_hasta__gt=hoy)
    )
    # Por el largo del número antes que por el número: así «902» va antes que «1001» sin convertir nada.
    return Unidad.objects.annotate(vinculos_vigentes=Count("vinculos", filter=vigente)).order_by(
        F("agrupacion__orden").asc(nulls_last=True), "piso", Length("numero"), "numero", "nombre"
    )


def destinatarios(unidad, hecho):
    """Las personas que deben enterarse de ese hecho sobre esa unidad."""
    vinculos = VinculoUnidad.objects.vigentes().filter(unidad=unidad).filter(VINCULOS_POR_HECHO[hecho])
    return Persona.objects.filter(pk__in=vinculos.values("persona_id"))


def unidades_de(persona):
    """Las unidades del conjunto activo sobre las que la persona tiene un vínculo vigente."""
    return Unidad.objects.filter(pk__in=VinculoUnidad.objects.vigentes().filter(persona=persona).values("unidad_id"))


def unidades_para_solicitar(persona):
    """Las unidades a cuyo nombre la persona puede solicitar: vínculo vigente y `reside` (maestro §5.10)."""
    vinculos = VinculoUnidad.objects.vigentes().filter(persona=persona, reside=True)
    return Unidad.objects.filter(pk__in=vinculos.values("unidad_id")).order_by("nombre")


def crear_unidad(actor, nombre):
    try:
        with transaction.atomic():
            unidad = Unidad.objects.create(nombre=nombre)
            auditoria.registrar(actor, "unidad.crear", "Unidad", unidad.id, despues={"nombre": nombre})
    except IntegrityError as error:
        if "unidad_nombre_unico_en_conjunto" in str(error):
            raise NombreRepetido() from error
        raise
    return unidad


def existentes_para(propuestas):
    """Lo que ya está guardado de lo que se propone: agrupaciones por su clave y nombres de vivienda."""
    claves = [estructura.clave(p.nombre_completo) for p in propuestas if p.nombre_completo]
    agrupaciones = {agrupacion.clave: agrupacion for agrupacion in Agrupacion.objects.filter(clave__in=claves)}
    nombres = [vivienda.nombre for propuesta in propuestas for vivienda in propuesta.viviendas]
    repetidas = set(Unidad.objects.filter(nombre__in=nombres).values_list("nombre", flat=True))
    return agrupaciones, repetidas


def resumen_de_estructura(tipo_vivienda, propuestas, agrupaciones, repetidas):
    filas = []
    for propuesta in propuestas:
        existente = agrupaciones.get(estructura.clave(propuesta.nombre_completo))
        if existente and existente.tipo_vivienda != tipo_vivienda:
            raise AgrupacionDeOtroTipo(propuesta.nombre_completo)
        nuevas = [vivienda for vivienda in propuesta.viviendas if vivienda.nombre not in repetidas]
        filas.append({
            "nombre": propuesta.nombre_completo,
            "existe": existente is not None,
            "viviendas": len(propuesta.viviendas),
            "nuevas": len(nuevas),
            "primera": propuesta.viviendas[0].nombre,
            "ultima": propuesta.viviendas[-1].nombre,
        })
    total = sum(fila["viviendas"] for fila in filas)
    nuevas = sum(fila["nuevas"] for fila in filas)
    return {
        "tipo_vivienda": tipo_vivienda,
        "total": total,
        "nuevas": nuevas,
        "repetidas": total - nuevas,
        "agrupaciones": filas,
    }


def previsualizar_estructura(descripcion):
    """Lo que se crearía, sin guardar nada. Es el mismo cálculo de `generar_estructura`."""
    propuestas = estructura.generar(descripcion)
    return resumen_de_estructura(descripcion["tipo_vivienda"], propuestas, *existentes_para(propuestas))


def generar_estructura(actor, descripcion):
    """Crea las agrupaciones y las viviendas que faltan, todas o ninguna. Las que ya existen se omiten."""
    tipo = descripcion["tipo_vivienda"]
    propuestas = estructura.generar(descripcion)
    # bulk_create se salta save(), así que el conjunto se fija aquí: siempre el activo.
    conjunto_id = conjunto_activo_id()
    try:
        with transaction.atomic():
            agrupaciones, repetidas = existentes_para(propuestas)
            resumen = resumen_de_estructura(tipo, propuestas, agrupaciones, repetidas)
            orden = Agrupacion.objects.aggregate(ultimo=Max("orden"))["ultimo"] or 0
            nuevas = []
            for propuesta in propuestas:
                agrupacion = None
                if propuesta.nombre_completo:
                    clave = estructura.clave(propuesta.nombre_completo)
                    agrupacion = agrupaciones.get(clave)
                    if agrupacion is None:
                        orden += 1
                        agrupacion = Agrupacion.objects.create(
                            etiqueta=propuesta.etiqueta,
                            nombre=propuesta.nombre,
                            clave=clave,
                            tipo_vivienda=tipo,
                            orden=orden,
                        )
                nuevas += [
                    Unidad(
                        conjunto_id=conjunto_id,
                        nombre=vivienda.nombre,
                        tipo=tipo,
                        agrupacion=agrupacion,
                        numero=vivienda.numero,
                        piso=vivienda.piso,
                    )
                    for vivienda in propuesta.viviendas
                    if vivienda.nombre not in repetidas
                ]
            Unidad.objects.bulk_create(nuevas)
            if nuevas:
                auditoria.registrar(
                    actor,
                    "unidad.generar",
                    "Unidad",
                    despues={
                        "tipo_vivienda": tipo,
                        "nuevas": resumen["nuevas"],
                        "repetidas": resumen["repetidas"],
                        "agrupaciones": [fila["nombre"] for fila in resumen["agrupaciones"]],
                    },
                )
    except IntegrityError as error:
        raise EstructuraCambiada() from error
    return resumen


def resumen_de_agrupaciones():
    """Las agrupaciones del conjunto activo con sus viviendas, y cuántas viviendas no tienen agrupación."""
    return {
        "agrupaciones": Agrupacion.objects.annotate(viviendas=Count("unidades")).order_by("orden"),
        "sin_agrupar": Unidad.objects.filter(agrupacion__isnull=True).count(),
        "total": Unidad.objects.count(),
    }


def detalle_de_unidad(unidad):
    """Vínculos vigentes y el histórico: los cerrados y los que todavía no empiezan."""
    vinculos = VinculoUnidad.objects.filter(unidad=unidad).select_related("persona").order_by("-vigencia_desde")
    vigentes = list(vinculos.vigentes())
    ids_vigentes = {vinculo.id for vinculo in vigentes}
    return {"vigentes": vigentes, "historicos": [v for v in vinculos if v.id not in ids_vigentes]}


def datos_del_vinculo(vinculo):
    return {
        "persona": vinculo.persona_id,
        "unidad": vinculo.unidad_id,
        "tipo": vinculo.tipo,
        "reside": vinculo.reside,
        "vigencia_desde": vinculo.vigencia_desde,
        "vigencia_hasta": vinculo.vigencia_hasta,
    }


def registrar_vinculo(actor, unidad, persona_id, tipo, reside, vigencia_desde=None):
    """Solo para quien ya tiene un rol vigente en el conjunto: así no se sondean personas ajenas (P3)."""
    en_el_conjunto = Asignacion.objects.vigentes().filter(persona_id=persona_id, conjunto_id=conjunto_activo_id())
    if not en_el_conjunto.exists():
        raise PersonaSinAsignacion()
    abiertos = VinculoUnidad.objects.filter(unidad=unidad, persona_id=persona_id, tipo=tipo)
    if abiertos.filter(vigencia_hasta__isnull=True).exists() or abiertos.vigentes().exists():
        raise VinculoDuplicado()
    try:
        with transaction.atomic():
            vinculo = VinculoUnidad.objects.create(
                unidad=unidad,
                persona_id=persona_id,
                tipo=tipo,
                reside=reside,
                vigencia_desde=vigencia_desde or timezone.localdate(),
            )
            auditoria.registrar(actor, "vinculo.registrar", "VinculoUnidad", vinculo.id, despues=datos_del_vinculo(vinculo))
    except IntegrityError as error:
        # Dos registros iguales a la vez: la base decide.
        if "vinculo_vigente_unico" in str(error):
            raise VinculoDuplicado() from error
        raise
    return vinculo


def cerrar_vinculo(actor, vinculo, vigencia_hasta=None):
    """`vigencia_hasta` es el primer día sin el vínculo; por defecto, hoy (plan P5). La fila se conserva."""
    vigencia_hasta = vigencia_hasta or timezone.localdate()
    if vinculo.vigencia_hasta is not None:
        raise VinculoYaCerrado()
    if vigencia_hasta < vinculo.vigencia_desde:
        raise CierreAntesDelInicio()
    antes = datos_del_vinculo(vinculo)
    with transaction.atomic():
        vinculo.vigencia_hasta = vigencia_hasta
        vinculo.save(update_fields=["vigencia_hasta"])
        auditoria.registrar(
            actor, "vinculo.cerrar", "VinculoUnidad", vinculo.id, antes=antes, despues=datos_del_vinculo(vinculo)
        )
    return vinculo
