"""Pago de la administración por vivienda y mes (HU-35). No sabe nada de HTTP.

El sistema no verifica el dinero ni lo mueve: registra que una persona reportó un pago y que otra de
la administración lo confirmó. No hay monto, saldo ni sanción. La cédula sirve para buscar y no sale
de aquí: el buscador filtra en el servidor y las filas no la traen.
"""
import unicodedata

from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.utils import timezone

from apps.auditoria import servicios as auditoria
from apps.comun.archivos import comprobantes
from apps.pagos import periodos
from apps.pagos.models import Comprobante, PagoDeAdministracion
from apps.personas.models import normalizar_documento
from apps.unidades.models import Unidad
from apps.unidades.servicios import unidades_de, unidades_del_conjunto

SIN_REPORTE, REPORTADO, CONFIRMADO = "sin_reporte", "reportado", "confirmado"
# Una palabra de solo dígitos y de este largo se compara como prefijo del documento: con «5» se busca la
# etapa 5, no a quien tiene una cédula que empieza por 5.
MINIMO_PARA_DOCUMENTO = 5
# Cuánto atrás y cuánto adelante puede reportar un residente (plan P10). Administración abre cualquier mes.
MESES_ATRAS_PARA_REPORTAR, MESES_ADELANTE_PARA_REPORTAR = 11, 1
MESES_QUE_VE_EL_RESIDENTE = 6


class UnidadNoEncontrada(Exception):
    """La vivienda no existe en el conjunto activo o no es de quien pregunta."""


class PeriodoNoPermitido(Exception):
    """El mes está fuera de la ventana en la que un residente puede reportar."""


class YaConfirmado(Exception):
    """Ese mes ya tiene el check: no se reporta de nuevo (plan P5)."""


class ComprobanteInvalido(Exception):
    """El archivo no sirve como comprobante. Trae el mensaje para quien lo subió."""

    def __init__(self, mensaje):
        super().__init__(mensaje)
        self.mensaje = mensaje


def estado_de(pago):
    """`sin_reporte`, `reportado` o `confirmado`, calculado de los hechos que guarda la fila (plan P3).

    `pago` puede ser `None`: una vivienda sin fila está «sin reporte».
    """
    if pago is None:
        return SIN_REPORTE
    if pago.confirmado_por_id is not None:
        return CONFIRMADO
    if pago.reportado_por_id is not None:
        return REPORTADO
    return SIN_REPORTE


def sin_tildes(texto):
    """Minúsculas y sin marcas diacríticas: «Gómez» y «gomez» son lo mismo."""
    descompuesto = unicodedata.normalize("NFD", str(texto))
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn").lower()


def palabras_de(consulta):
    """Las palabras de lo escrito, sin tildes y sin las que son solo signos."""
    return [p for p in sin_tildes(consulta).split() if any(c.isalnum() for c in p)]


def coincide(unidad, consulta):
    """Si la vivienda responde a lo buscado (plan P7): su nombre, el de alguien con vínculo vigente o un documento.

    Todas las palabras tienen que aparecer. Una de solo dígitos y 5 o más de largo, ya normalizada
    como un documento, también cuenta si es prefijo del documento de alguien con vínculo vigente.
    """
    vinculos = getattr(unidad, "vinculos_de_hoy", [])
    texto = " ".join([sin_tildes(unidad.nombre)] + [
        sin_tildes(f"{v.persona.nombres} {v.persona.apellidos}") for v in vinculos
    ])
    documentos = [normalizar_documento(v.persona.numero_documento) for v in vinculos]
    for palabra in palabras_de(consulta):
        if palabra in texto:
            continue
        documento = normalizar_documento(palabra)
        if (
            documento.isdigit()
            and len(documento) >= MINIMO_PARA_DOCUMENTO
            and any(numero.startswith(documento) for numero in documentos)
        ):
            continue
        return False
    return True


def pagos_del_periodo(periodo):
    """`{unidad_id: pago}` del mes, en una sola consulta y sin el contenido de los archivos."""
    comprobantes_del_pago = Comprobante.objects.defer("contenido").select_related("subido_por").order_by("-subido_en")
    consulta = (
        PagoDeAdministracion.objects.filter(periodo=periodo)
        .select_related("reportado_por", "confirmado_por")
        .prefetch_related(Prefetch("comprobantes", queryset=comprobantes_del_pago, to_attr="comprobantes_cargados"))
    )
    return {pago.unidad_id: pago for pago in consulta}


def filas_del_periodo(periodo, buscar=""):
    """Una fila por vivienda del conjunto activo: la unidad con sus vínculos de hoy y su pago del mes, o `None`.

    Se parte de las viviendas y se les pega el pago si existe: una vivienda sin pago también es una fila.
    """
    pagos = pagos_del_periodo(periodo)
    filas = []
    for unidad in unidades_del_conjunto(con_personas=True):
        if buscar and not coincide(unidad, buscar):
            continue
        filas.append({"unidad": unidad, "pago": pagos.get(unidad.id)})
    return filas


def fila_de(unidad_id, periodo):
    """La fila de una vivienda y un mes, como las de `filas_del_periodo`. `UnidadNoEncontrada` si no existe."""
    unidad = unidades_del_conjunto(con_personas=True).filter(pk=unidad_id).first()
    if unidad is None:
        raise UnidadNoEncontrada()
    return {"unidad": unidad, "pago": pagos_del_periodo(periodo).get(unidad.id)}


def pago_bloqueado(unidad, periodo, crear):
    """La fila del mes con `select_for_update`; con `crear`, la crea si no existe. Va dentro de una transacción.

    Dos clics a la vez sobre un mes sin fila: los dos intentan crearla, la base acepta una y el otro la lee.
    """
    consulta = PagoDeAdministracion.objects.select_for_update().filter(unidad=unidad, periodo=periodo)
    pago = consulta.first()
    if pago is None and crear:
        try:
            with transaction.atomic():
                pago = PagoDeAdministracion.objects.create(unidad=unidad, periodo=periodo)
        except IntegrityError:
            pago = consulta.get()
    return pago


def confirmar(actor, unidad_id, periodo, confirmado=True):
    """Pone o quita el check de la vivienda y el mes. Audita `pago.confirmar` o `pago.desmarcar` solo si algo cambió.

    Es idempotente: marcar lo marcado no cambia nada ni duplica la auditoría. Quitar el check deja
    `confirmado_*` en `None`; quién lo había puesto queda en la auditoría (`antes`). Administración
    puede marcar sin comprobante: el pago pudo llegar por otro canal (plan P4).
    """
    unidad = Unidad.objects.filter(pk=unidad_id).first()
    if unidad is None:
        raise UnidadNoEncontrada()
    with transaction.atomic():
        pago = pago_bloqueado(unidad, periodo, crear=confirmado)
        if pago is None:
            return None
        if confirmado and pago.confirmado_por_id is None:
            ahora = timezone.now()
            pago.confirmado_por = actor
            pago.confirmado_en = ahora
            pago.save(update_fields=["confirmado_por", "confirmado_en"])
            auditoria.registrar(
                actor,
                "pago.confirmar",
                "PagoDeAdministracion",
                pago.id,
                antes={"confirmado": False},
                despues={"confirmado": True, "unidad": str(unidad.id), "periodo": periodos.texto_de(periodo)},
            )
        elif not confirmado and pago.confirmado_por_id is not None:
            antes = {
                "confirmado": True,
                "confirmado_por": str(pago.confirmado_por_id),
                "confirmado_en": pago.confirmado_en,
            }
            pago.confirmado_por = None
            pago.confirmado_en = None
            pago.save(update_fields=["confirmado_por", "confirmado_en"])
            auditoria.registrar(
                actor,
                "pago.desmarcar",
                "PagoDeAdministracion",
                pago.id,
                antes=antes,
                despues={"confirmado": False, "unidad": str(unidad.id), "periodo": periodos.texto_de(periodo)},
            )
    return pago


def unidades_para_reportar(persona):
    """Las viviendas sobre las que la persona tiene vínculo vigente, resida o no (D6 a)."""
    return unidades_de(persona)


def reportar(actor, unidad_id, periodo, nombre, contenido, hoy=None):
    """Crea o toma el pago del mes, le agrega el comprobante, fija `reportado_*` y audita `pago.reportar`.

    El tipo del archivo lo decide su firma, no la extensión ni lo que diga el navegador. Subir otro
    comprobante no borra el anterior; el vigente es el más reciente (plan P5).
    """
    unidad = unidades_para_reportar(actor).filter(pk=unidad_id).first()
    if unidad is None:
        raise UnidadNoEncontrada()
    actual = periodos.actual(hoy)
    if not periodos.sumar_meses(actual, -MESES_ATRAS_PARA_REPORTAR) <= periodo <= periodos.sumar_meses(
        actual, MESES_ADELANTE_PARA_REPORTAR
    ):
        raise PeriodoNoPermitido()
    try:
        datos = comprobantes.validar_comprobante(contenido)
    except comprobantes.ArchivoInvalido as error:
        raise ComprobanteInvalido(error.mensaje) from error
    with transaction.atomic():
        pago = pago_bloqueado(unidad, periodo, crear=True)
        if pago.confirmado_por_id is not None:
            raise YaConfirmado()
        comprobante = Comprobante.objects.create(
            pago=pago, contenido=contenido, nombre=(nombre or "").strip()[:120] or "comprobante", subido_por=actor, **datos
        )
        pago.reportado_por = actor
        pago.reportado_en = comprobante.subido_en
        pago.save(update_fields=["reportado_por", "reportado_en"])
        auditoria.registrar(
            actor,
            "pago.reportar",
            "PagoDeAdministracion",
            pago.id,
            despues={
                "unidad": str(unidad.id),
                "periodo": periodos.texto_de(periodo),
                "comprobante": str(comprobante.id),
                "tipo": datos["tipo"],
                "huella": datos["huella"],
            },
        )
    return pago


def mis_pagos(persona, hoy=None):
    """Por cada vivienda de la persona, sus últimos 6 periodos, el más reciente primero, con su pago o `None`."""
    actual = periodos.actual(hoy)
    meses = [periodos.sumar_meses(actual, -n) for n in range(MESES_QUE_VE_EL_RESIDENTE)]
    unidades = list(unidades_para_reportar(persona).order_by("nombre"))
    comprobantes_del_pago = Comprobante.objects.defer("contenido").select_related("subido_por").order_by("-subido_en")
    pagos = {}
    consulta = (
        PagoDeAdministracion.objects.filter(unidad__in=unidades, periodo__in=meses)
        .select_related("reportado_por", "confirmado_por")
        .prefetch_related(Prefetch("comprobantes", queryset=comprobantes_del_pago, to_attr="comprobantes_cargados"))
    )
    for pago in consulta:
        pagos[(pago.unidad_id, pago.periodo)] = pago
    return [
        {"unidad": unidad, "periodos": [{"periodo": mes, "pago": pagos.get((unidad.id, mes))} for mes in meses]}
        for unidad in unidades
    ]


def comprobante_para(persona, puede_ver_todos, comprobante_id):
    """El comprobante con su contenido si la persona puede verlo; si no, `None` (plan B2.2).

    Lo ve quien gestiona pagos (`pago.ver`) y quien reporta con vínculo vigente con la vivienda de ese pago.
    La respuesta es la misma si no existe o si no es suyo: no se dice cuál.
    """
    comprobante = Comprobante.objects.select_related("pago").filter(pk=comprobante_id).first()
    if comprobante is None:
        return None
    if puede_ver_todos or unidades_de(persona).filter(pk=comprobante.pago.unidad_id).exists():
        return comprobante
    return None
