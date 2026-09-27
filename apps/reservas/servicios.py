"""Flujo de reserva del conjunto activo (maestro §5.1, HU-11). No sabe nada de HTTP.

El orden de llegada decide quién puede pedir: tomar el bloqueo de una franja es un INSERT que
el índice único parcial acepta una sola vez. La expiración se evalúa al principio de cada
consulta y cada acción de este módulo, sin procesos en segundo plano.

Plan D7 a: por ahora no se revisa `conjunto.operativo`. Ningún conjunto puede quedar operativo
hasta HU-33 (Sprint 6), y sin esto los Sprints 3 y 4 no se podrían demostrar.
"""
from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.formats import date_format

from apps.areas.servicios import franjas_del_dia
from apps.auditoria import servicios as auditoria
from apps.comun.bloqueo import bloqueo
from apps.notificaciones.canal import Aviso, notificar
from apps.permisos.catalogo import Rol
from apps.permisos.models import Asignacion
from apps.reglas.catalogo import TipoDeRegla
from apps.reglas.evaluador import evaluar
from apps.reglas.servicios import reglas_vigentes
from apps.reservas.models import BLOQUEANTES, EstadoSolicitud, MotivoLiberacion, Solicitud
from apps.unidades.models import Unidad
from apps.unidades.servicios import unidades_para_solicitar

# Constante del sistema, no regla beta (maestro §5.1, plan P11).
DURACION_BLOQUEO = timedelta(minutes=3)

# Cómo ve una franja quien consulta. Nunca dice quién la tiene.
ESTADO_DE_FRANJA = {
    EstadoSolicitud.EN_SOLICITUD: "en_solicitud",
    EstadoSolicitud.APARTADA: "apartada",
    EstadoSolicitud.RESERVADA: "reservada",
}


class SinUnidadParaSolicitar(Exception):
    """La persona no tiene ningún vínculo vigente con `reside` (plan P8)."""


class AreaNoDisponible(Exception):
    """El área está inactiva o en mantenimiento (HU-09)."""


class FranjaInvalida(Exception):
    """La franja no existe en el horario del área o ya empezó."""


class FranjaOcupada(Exception):
    """Otra persona tiene la franja en trámite, apartada o reservada."""


class YaTienesUnBloqueo(Exception):
    """La persona ya tiene una solicitud en trámite en el conjunto (plan D3 a)."""

    def __init__(self, solicitud_id):
        super().__init__(solicitud_id)
        self.solicitud_id = solicitud_id


class NoEstaEnTramite(Exception):
    """La solicitud ya no está `EN_SOLICITUD`: se envió, venció o se liberó."""


class SolicitudNoEncontrada(Exception):
    """No existe en el conjunto activo o es de otra persona."""


class UnidadNoEncontrada(Exception):
    """La unidad elegida no existe en el conjunto activo."""


class BloqueoVencido(Exception):
    """Se acabaron los 3 minutos antes de enviar. La solicitud quedó `EXPIRADA`."""


class IncumpleReglas(Exception):
    """La solicitud no cumple una o más reglas. Trae todos los motivos, no solo el primero."""

    def __init__(self, motivos):
        super().__init__(motivos)
        self.motivos = motivos


def inicio_de(fecha, hora):
    """El momento en que empieza la franja, en la zona horaria del conjunto (America/Bogota)."""
    return timezone.make_aware(datetime.combine(fecha, hora))


def expirar_vencidas(ahora=None):
    return bloqueo.expirar_vencidos(
        Solicitud.objects,
        campo_vence="bloqueo_vence_en",
        estado_activo=EstadoSolicitud.EN_SOLICITUD,
        estado_expirado=EstadoSolicitud.EXPIRADA,
        ahora=ahora or timezone.now(),
    )


def franjas(persona, area, fecha):
    """Las franjas del día con su estado: libre, en_solicitud, apartada, reservada, pasada, propia o no_disponible."""
    expirar_vencidas()
    bloques = franjas_del_dia(area, fecha)
    if not area.activo or area.en_mantenimiento:
        return [{"hora_inicio": inicio, "hora_fin": fin, "estado": "no_disponible"} for inicio, fin in bloques]
    ocupadas = {
        solicitud.hora_inicio: solicitud
        for solicitud in Solicitud.objects.filter(area=area, fecha=fecha, estado__in=BLOQUEANTES)
    }
    ahora = timezone.now()
    resultado = []
    for inicio, fin in bloques:
        solicitud = ocupadas.get(inicio)
        if inicio_de(fecha, inicio) <= ahora:
            estado = "pasada"
        elif solicitud is None:
            estado = "libre"
        elif solicitud.persona_id == persona.id:
            estado = "propia"
        else:
            estado = ESTADO_DE_FRANJA[solicitud.estado]
        resultado.append({"hora_inicio": inicio, "hora_fin": fin, "estado": estado})
    return resultado


def tomar_bloqueo(persona, area, fecha, hora_inicio):
    """Crea la solicitud `EN_SOLICITUD` con 3 minutos exclusivos para llenarla y enviarla (HU-11)."""
    expirar_vencidas()
    if not unidades_para_solicitar(persona).exists():
        raise SinUnidadParaSolicitar()
    if not area.activo or area.en_mantenimiento:
        raise AreaNoDisponible()
    hora_fin = dict(franjas_del_dia(area, fecha)).get(hora_inicio)
    ahora = timezone.now()
    if hora_fin is None or inicio_de(fecha, hora_inicio) <= ahora:
        raise FranjaInvalida()

    def crear():
        return Solicitud.objects.create(
            area=area,
            persona=persona,
            fecha=fecha,
            hora_inicio=hora_inicio,
            hora_fin=hora_fin,
            estado=EstadoSolicitud.EN_SOLICITUD,
            bloqueo_vence_en=ahora + DURACION_BLOQUEO,
        )

    try:
        return bloqueo.tomar(crear)
    except bloqueo.RecursoOcupado as ocupado:
        if ocupado.restriccion == "solicitud_un_bloqueo_por_persona":
            en_curso = Solicitud.objects.filter(persona=persona, estado=EstadoSolicitud.EN_SOLICITUD).first()
            raise YaTienesUnBloqueo(en_curso.id if en_curso else None) from ocupado
        raise FranjaOcupada() from ocupado


def liberar(persona, solicitud):
    """La dueña suelta el bloqueo a propósito: la franja queda libre de inmediato y no gasta oportunidad (R9)."""
    expirar_vencidas()
    # Condicionado al estado: si dos liberaciones llegan a la vez, o el bloqueo ya venció, solo una cambia algo.
    cambiadas = Solicitud.objects.filter(pk=solicitud.pk, persona=persona, estado=EstadoSolicitud.EN_SOLICITUD).update(
        estado=EstadoSolicitud.LIBERADA, motivo_liberacion=MotivoLiberacion.VOLUNTARIA
    )
    if not cambiadas:
        raise NoEstaEnTramite()
    solicitud.refresh_from_db()
    return solicitud


def solicitudes_de(persona):
    """Solo las propias (plan P14). La bandeja del administrador es HU-14."""
    expirar_vencidas()
    return Solicitud.objects.filter(persona=persona).select_related("area", "unidad").order_by("-creada_en")


def detalle(persona, solicitud_id):
    """La solicitud si es de la persona; si no, None."""
    return solicitudes_de(persona).filter(pk=solicitud_id).first()


def avisos(solicitud):
    """Lo que el panel de confirmación resalta sin impedir el envío (HU-12, plan D9 a).

    «Alta demanda» llega con PB-24 (Sprint 4).
    """
    if solicitud.estado != EstadoSolicitud.EN_SOLICITUD:
        return []
    resultado = []
    if inicio_de(solicitud.fecha, solicitud.hora_inicio) - timezone.now() < timedelta(hours=24):
        resultado.append("menos_de_24h")
    hoy = timezone.localdate()
    maximas = reglas_vigentes(solicitud.area, hoy).filter(tipo=TipoDeRegla.ANTICIPACION_MAXIMA)
    if any(solicitud.fecha == hoy + timedelta(days=regla.parametros["dias"]) for regla in maximas):
        resultado.append("limite_de_anticipacion")
    otras = Solicitud.objects.filter(
        persona_id=solicitud.persona_id,
        estado__in=[EstadoSolicitud.APARTADA, EstadoSolicitud.RESERVADA],
        fecha__gte=hoy,
    ).exclude(pk=solicitud.pk)
    if otras.exists():
        resultado.append("otra_solicitud")
    return resultado


def segundos_restantes(solicitud):
    """Los calcula el servidor: el reloj del navegador no decide si un bloqueo venció."""
    if solicitud.estado != EstadoSolicitud.EN_SOLICITUD:
        return 0
    return max(0, int((solicitud.bloqueo_vence_en - timezone.now()).total_seconds()))


def dia_en_letras(solicitud):
    return date_format(solicitud.fecha, r"l j \d\e F \d\e Y").lower()


def avisar_a_la_administracion(solicitud):
    """La solicitud apartada queda en manos de quien tiene Administración vigente en el conjunto."""
    administradores = Asignacion.objects.vigentes().filter(conjunto_id=solicitud.conjunto_id, rol=Rol.ADMINISTRACION)
    cuerpo = (
        f"{solicitud.area.nombre} el {dia_en_letras(solicitud)}, de {solicitud.hora_inicio:%H:%M} a "
        f"{solicitud.hora_fin:%H:%M}, para {solicitud.asistentes} asistentes. Motivo: {solicitud.motivo}."
    )
    aviso = Aviso("Nueva solicitud de reserva", cuerpo, origen="reserva", referencia=solicitud.id)
    notificar(aviso, list(administradores.values_list("persona_id", flat=True).distinct()))


def enviar(persona, solicitud_id, *, unidad_id, motivo, asistentes, observaciones=""):
    """Evalúa la solicitud contra todas las reglas y la aparta, o la libera con todos los motivos (HU-13).

    El cambio de estado se guarda antes de lanzar cualquier error: si se lanzara dentro de la
    transacción, el rollback desharía la expiración o la liberación.
    """
    expirar_vencidas()
    error = None
    with transaction.atomic():
        solicitud = Solicitud.objects.select_for_update().select_related("area").filter(pk=solicitud_id).first()
        if solicitud is None or solicitud.persona_id != persona.id:
            raise SolicitudNoEncontrada()
        if solicitud.estado == EstadoSolicitud.EXPIRADA:
            raise BloqueoVencido()
        if solicitud.estado != EstadoSolicitud.EN_SOLICITUD:
            raise NoEstaEnTramite()
        if solicitud.bloqueo_vence_en <= timezone.now():
            # Venció entre la expiración de arriba y el bloqueo de la fila.
            solicitud.estado = EstadoSolicitud.EXPIRADA
            solicitud.save(update_fields=["estado"])
            error = BloqueoVencido()
        else:
            unidad = Unidad.objects.filter(pk=unidad_id).first()
            if unidad is None:
                raise UnidadNoEncontrada()
            solicitud.unidad = unidad
            solicitud.motivo = motivo
            solicitud.asistentes = asistentes
            solicitud.observaciones = observaciones
            resultados = evaluar(solicitud)
            solicitud.evaluacion = [resultado.como_dict() for resultado in resultados]
            solicitud.evaluada_en = timezone.now()
            motivos = [resultado.motivo for resultado in resultados if not resultado.cumple]
            if motivos:
                # El bloqueo se suelta: la franja queda libre para otro (plan D2 a).
                solicitud.estado = EstadoSolicitud.LIBERADA
                solicitud.motivo_liberacion = MotivoLiberacion.REGLAS
                accion = "reserva.liberar_por_reglas"
                error = IncumpleReglas(motivos)
            else:
                solicitud.estado = EstadoSolicitud.APARTADA
                solicitud.enviada_en = timezone.now()
                accion = "reserva.enviar"
            solicitud.save()
            auditoria.registrar(
                persona,
                accion,
                "Solicitud",
                solicitud.id,
                antes={"estado": EstadoSolicitud.EN_SOLICITUD},
                despues={"estado": solicitud.estado, "unidad": unidad.id, "asistentes": asistentes},
                detalle={"evaluacion": solicitud.evaluacion},
            )
            if not motivos:
                avisar_a_la_administracion(solicitud)
    if error:
        raise error
    return solicitud
