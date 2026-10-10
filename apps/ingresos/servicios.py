"""Ingreso a zonas con aforo simultáneo (plan de zonas con ingreso). No sabe nada de HTTP.

No hay procesos en segundo plano: toda lectura y toda acción empieza por `dar_salida_a_vencidos`,
que libera a quien ya cumplió su tiempo. El último cupo lo decide una transacción que toma la fila
del área (el aforo es una suma, no una fila única que un índice pueda custodiar); que una persona
tenga un solo ingreso abierto sí lo decide un índice único parcial.
"""
from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone

from apps.areas.models import Area, ModoDeUso
from apps.auditoria import servicios as auditoria
from apps.comun.bloqueo import bloqueo
from apps.ingresos.evaluador import evaluar
from apps.ingresos.models import EstadoIngreso, Ingreso
from apps.notificaciones.canal import Aviso, notificar
from apps.reglas import catalogo
from apps.reglas.models import Regla
from apps.unidades import servicios as unidades
from apps.unidades.models import Unidad, VinculoUnidad

MENSAJE_YA_ADENTRO = "La persona ya está adentro de una zona."


class AreaNoEncontrada(Exception):
    """El área no existe en el conjunto activo."""


class AreaSinIngreso(Exception):
    """El área es con reserva: el ingreso no aplica (plan P4)."""


class ResidenteNoEncontrado(Exception):
    """La persona no vive en el conjunto activo. No se dice si existe en otro."""


class UnidadNoEncontrada(Exception):
    """La vivienda no existe en el conjunto activo."""


class IncumpleReglas(Exception):
    """El ingreso no cumple una o más reglas. Trae todos los motivos, no solo el primero."""

    def __init__(self, motivos):
        super().__init__(motivos)
        self.motivos = motivos


class IngresoNoEncontrado(Exception):
    """No existe en el conjunto activo."""


class YaSalio(Exception):
    """El ingreso ya no está adentro: salió o se le cumplió el tiempo."""


def dar_salida_a_vencidos(ahora=None):
    """Pasa a `VENCIDO` a quien ya cumplió su tiempo, con su hora prevista como salida, y avisa al residente (plan P13).

    Es idempotente, y el canal no repite un aviso con el mismo origen y referencia. Devuelve cuántos liberó.
    """
    ahora = ahora or timezone.now()
    with transaction.atomic():
        vencidos = list(
            Ingreso.objects.select_for_update(of=("self",))
            .select_related("area")
            .filter(estado=EstadoIngreso.ADENTRO, salida_prevista_en__lte=ahora)
        )
        for ingreso in vencidos:
            ingreso.estado = EstadoIngreso.VENCIDO
            ingreso.salida_en = ingreso.salida_prevista_en
            ingreso.save(update_fields=["estado", "salida_en"])
            hora = timezone.localtime(ingreso.salida_prevista_en)
            aviso = Aviso(
                f"Se cumplió tu tiempo en {ingreso.area.nombre}",
                f"Tu tiempo en {ingreso.area.nombre} terminó a las {hora:%H:%M}. Si sigues adentro, "
                "te pedimos salir para dejar el puesto a otra persona.",
                origen="ingreso",
                referencia=ingreso.id,
            )
            notificar(aviso, [ingreso.persona_id])
    return len(vencidos)


def ocupacion(area):
    """Las personas adentro: cada ingreso abierto cuenta uno más sus acompañantes (plan P10)."""
    total = Ingreso.objects.filter(area=area, estado=EstadoIngreso.ADENTRO).aggregate(
        ingresos=Count("id"), acompanantes=Sum("acompanantes")
    )
    return total["ingresos"] + (total["acompanantes"] or 0)


def estado_de_apertura(area, ahora=None):
    """Si la zona atiende ahora y, si no, por qué. Es lo que lee quien consulta los cupos."""
    ahora = timezone.localtime(ahora or timezone.now())
    if not area.activo:
        return False, "La zona está desactivada."
    if area.en_mantenimiento:
        return False, "En mantenimiento."
    cierres = Regla.objects.vigentes(ahora.date()).filter(area=area, tipo=catalogo.TipoDeRegla.DIAS_QUE_NO_ABRE)
    for regla in cierres:
        motivos = catalogo.motivos_del_dia(ahora.date(), regla.parametros["renglones"])
        if motivos:
            return False, f"No abre hoy: {'; '.join(motivos)}."
    if not area.hora_apertura <= ahora.time() < area.hora_cierre:
        return False, f"Atiende de {area.hora_apertura:%H:%M} a {area.hora_cierre:%H:%M}."
    return True, ""


def zonas(ahora=None):
    """Las zonas activas con ingreso y sus cupos de este momento. Solo conteos, sin nombres (plan P17)."""
    dar_salida_a_vencidos(ahora)
    resultado = []
    for area in Area.objects.filter(modo_uso=ModoDeUso.INGRESO, activo=True).order_by("nombre"):
        adentro = ocupacion(area)
        abierta, motivo = estado_de_apertura(area, ahora)
        resultado.append(
            {
                "area": area,
                "adentro": adentro,
                "cupos": max(0, area.aforo_maximo - adentro),
                "abierta_ahora": abierta,
                "motivo_cierre": motivo,
            }
        )
    return resultado


def buscar_residente(actor, numero_documento):
    """Quienes viven en el conjunto con ese documento. Cada búsqueda queda en la auditoría, sin el documento."""
    encontrados = unidades.residentes_por_documento(numero_documento)
    auditoria.registrar(actor, "ingreso.buscar_residente", "Persona", detalle={"encontrados": len(encontrados)})
    return encontrados


def salida_prevista(area, entrada):
    """La entrada más la permanencia del área, sin pasar de la hora de cierre de ese día (plan P12)."""
    prevista = entrada + timedelta(minutes=area.permanencia_maxima_minutos)
    cierre = timezone.make_aware(datetime.combine(timezone.localtime(entrada).date(), area.hora_cierre))
    return min(prevista, cierre)


def registrar(actor, area_id, persona_id, unidad_id, acompanantes, ahora=None):
    """Evalúa el ingreso contra todas las reglas y lo registra, o lo rechaza con todos los motivos.

    La fila del área se toma con `select_for_update`: dos registros a la misma zona pasan de a uno,
    y el segundo ve la ocupación que dejó el primero. Como en `reservas.enviar`, el error se lanza
    después de la transacción: dentro, el rollback desharía la salida automática de los vencidos.
    """
    ahora = ahora or timezone.now()
    error = None
    with transaction.atomic():
        area = Area.objects.select_for_update().filter(pk=area_id).first()
        if area is None:
            raise AreaNoEncontrada()
        if area.modo_uso != ModoDeUso.INGRESO:
            raise AreaSinIngreso()
        unidad = Unidad.objects.filter(pk=unidad_id).first()
        if unidad is None:
            raise UnidadNoEncontrada()
        residente = (
            VinculoUnidad.objects.vigentes()
            .select_related("persona")
            .filter(persona_id=persona_id, reside=True)
            .first()
        )
        if residente is None:
            raise ResidenteNoEncontrado()
        dar_salida_a_vencidos(ahora)
        ingreso = Ingreso(
            area=area,
            persona=residente.persona,
            unidad=unidad,
            acompanantes=acompanantes,
            entrada_en=ahora,
            salida_prevista_en=salida_prevista(area, ahora),
            registrado_por=actor,
        )
        resultados = evaluar(ingreso, ocupacion(area))
        motivos = [resultado.motivo for resultado in resultados if not resultado.cumple]
        if motivos:
            error = IncumpleReglas(motivos)
        else:
            ingreso.evaluacion = [resultado.como_dict() for resultado in resultados]
            try:
                bloqueo.tomar(ingreso.save)
            except bloqueo.RecursoOcupado as ocupado:
                if ocupado.restriccion != "ingreso_uno_abierto_por_persona":
                    raise
                # Otra zona la registró en el mismo instante: la base decidió.
                error = IncumpleReglas([MENSAJE_YA_ADENTRO])
            else:
                auditoria.registrar(
                    actor,
                    "ingreso.registrar",
                    "Ingreso",
                    ingreso.id,
                    despues={
                        "area": area.id,
                        "persona": ingreso.persona_id,
                        "unidad": unidad.id,
                        "acompanantes": acompanantes,
                        "salida_prevista_en": ingreso.salida_prevista_en,
                    },
                    detalle={"evaluacion": ingreso.evaluacion},
                )
    if error:
        raise error
    return ingreso


def registrar_salida(actor, ingreso_id, ahora=None):
    """El vigilante marca que la persona se fue. Libera el cupo de ella y de sus acompañantes."""
    ahora = ahora or timezone.now()
    dar_salida_a_vencidos(ahora)
    with transaction.atomic():
        ingreso = (
            Ingreso.objects.select_for_update(of=("self",))
            .select_related("area", "persona")
            .filter(pk=ingreso_id)
            .first()
        )
        if ingreso is None:
            raise IngresoNoEncontrado()
        if ingreso.estado != EstadoIngreso.ADENTRO:
            raise YaSalio()
        ingreso.estado = EstadoIngreso.SALIO
        ingreso.salida_en = ahora
        ingreso.salida_registrada_por = actor
        ingreso.save(update_fields=["estado", "salida_en", "salida_registrada_por"])
        auditoria.registrar(
            actor,
            "ingreso.salida",
            "Ingreso",
            ingreso.id,
            antes={"estado": EstadoIngreso.ADENTRO},
            despues={"estado": EstadoIngreso.SALIO},
        )
    return ingreso


def con_detalle(ingresos):
    return ingresos.select_related("area", "persona", "unidad", "registrado_por", "salida_registrada_por")


def adentro(ahora=None):
    """Quién está adentro, por hora de entrada."""
    dar_salida_a_vencidos(ahora)
    return con_detalle(Ingreso.objects.filter(estado=EstadoIngreso.ADENTRO)).order_by("entrada_en")


def vencidos_de_hoy(ahora=None):
    """A quién se le cumplió el tiempo hoy: lo que el vigilante verifica en la puerta."""
    dar_salida_a_vencidos(ahora)
    hoy = timezone.localtime(ahora or timezone.now()).date()
    return con_detalle(Ingreso.objects.filter(estado=EstadoIngreso.VENCIDO, salida_en__date=hoy)).order_by("-salida_en")


def historial(area_id=None, fecha=None, ahora=None):
    """Todos los ingresos de un día (hoy si no se dice) y, si se pide, de una sola zona."""
    dar_salida_a_vencidos(ahora)
    fecha = fecha or timezone.localtime(ahora or timezone.now()).date()
    ingresos = con_detalle(Ingreso.objects.filter(entrada_en__date=fecha))
    if area_id is not None:
        ingresos = ingresos.filter(area_id=area_id)
    return ingresos.order_by("-entrada_en")
