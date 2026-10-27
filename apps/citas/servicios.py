"""Configuración del horario de atención semanal (HU-31)."""
from datetime import datetime, time, timedelta

from django.db import transaction
from django.utils import timezone

from apps.auditoria import servicios as auditoria
from apps.citas.models import Cita, EstadoCita, HorarioDeAtencion
from apps.comun.bloqueo import bloqueo
from apps.conjuntos.models import Conjunto


class FranjaDeCitaInvalida(Exception):
    """La franja no corresponde al horario o ya empezó."""


class FranjaDeCitaOcupada(Exception):
    """La franja ya está agendada."""


class CitaActivaExistente(Exception):
    """La persona ya tiene una cita futura."""


def _hora(valor):
    return time.fromisoformat(valor) if isinstance(valor, str) else valor


def horario_del_dia(dias, fecha):
    return next((dia for dia in dias if dia["dia"] == fecha.weekday()), None)


def franjas_del_dia(dias, fecha):
    """Bloques consecutivos de dos horas, sin cruzar el almuerzo ni exceder el horario."""
    dia = horario_del_dia(dias, fecha)
    if not dia or not dia["activo"]:
        return []
    inicio = _hora(dia["hora_inicio"])
    fin = _hora(dia["hora_fin"])
    descanso_inicio = _hora(dia["descanso_inicio"]) if dia["descanso_inicio"] else None
    descanso_fin = _hora(dia["descanso_fin"]) if dia["descanso_fin"] else None
    periodos = [(inicio, descanso_inicio), (descanso_fin, fin)] if descanso_inicio else [(inicio, fin)]
    franjas = []
    duracion = timedelta(hours=2)
    for comienzo, cierre in periodos:
        actual = datetime.combine(fecha, comienzo)
        limite = datetime.combine(fecha, cierre)
        while actual + duracion <= limite:
            fin_franja = actual + duracion
            franjas.append((actual.time(), fin_franja.time()))
            actual = fin_franja
    return franjas


def disponibilidad(persona, conjunto_id, fecha=None):
    expirar_citas()
    horario = HorarioDeAtencion.objects.filter(conjunto_id=conjunto_id).first()
    dias = horario.dias if horario else []
    ahora = timezone.localtime()
    citas = list(
        Cita.objects.filter(conjunto_id=conjunto_id, fecha=fecha, estado=EstadoCita.AGENDADA).order_by("hora_inicio")
    ) if fecha else []
    franjas = []
    for inicio, fin in franjas_del_dia(dias, fecha) if fecha else []:
        cita = next(
            (cita for cita in citas if cita.hora_inicio < fin and cita.hora_fin > inicio),
            None,
        )
        inicio_local = timezone.make_aware(datetime.combine(fecha, inicio))
        if inicio_local <= ahora:
            estado = "pasada"
        elif cita is None:
            estado = "libre"
        elif cita.persona_id == persona.id:
            estado = "propia"
        else:
            estado = "ocupada"
        franjas.append({"hora_inicio": inicio, "hora_fin": fin, "estado": estado})
    cita_propia = (
        citas_futuras(persona, ahora)
        .filter(conjunto_id=conjunto_id)
        .order_by("fecha", "hora_inicio")
        .first()
    )
    return {"horario": horario_actual(conjunto_id), "franjas": franjas, "cita_propia": cita_propia}


def citas_futuras(persona, ahora=None):
    ahora = ahora or timezone.localtime()
    return Cita.objects.filter(persona=persona, estado=EstadoCita.AGENDADA, vence_en__gt=ahora)


def expirar_citas(ahora=None):
    ahora = ahora or timezone.now()
    return bloqueo.expirar_vencidos(
        Cita.objects,
        campo_vence="vence_en",
        estado_activo=EstadoCita.AGENDADA,
        estado_expirado=EstadoCita.ATENDIDA,
        ahora=ahora,
    )


def citas_para_administracion(conjunto_id):
    expirar_citas()
    return Cita.objects.filter(conjunto_id=conjunto_id).select_related("persona").order_by(
        "fecha", "hora_inicio"
    )


def agendar(persona, conjunto_id, fecha, hora_inicio):
    """Agenda una franja exclusiva de dos horas, serializando por conjunto (R1)."""
    expirar_citas()
    ahora = timezone.localtime()

    def crear():
        conjunto = Conjunto.objects.select_for_update().get(pk=conjunto_id)
        horario = HorarioDeAtencion.objects.filter(conjunto=conjunto).first()
        dias = horario.dias if horario else []
        franjas = franjas_del_dia(dias, fecha)
        seleccionada = next(((inicio, fin) for inicio, fin in franjas if inicio == hora_inicio), None)
        if seleccionada is None:
            raise FranjaDeCitaInvalida()
        inicio, fin = seleccionada
        if fecha < ahora.date() or timezone.make_aware(datetime.combine(fecha, inicio)) <= ahora:
            raise FranjaDeCitaInvalida()
        if citas_futuras(persona, ahora).exists():
            raise CitaActivaExistente()
        if Cita.objects.filter(
            conjunto_id=conjunto_id,
            fecha=fecha,
            estado=EstadoCita.AGENDADA,
            hora_inicio__lt=fin,
            hora_fin__gt=inicio,
        ).exists():
            raise FranjaDeCitaOcupada()
        cita = Cita.objects.create(
            conjunto=conjunto,
            persona=persona,
            fecha=fecha,
            hora_inicio=inicio,
            hora_fin=fin,
            vence_en=timezone.make_aware(datetime.combine(fecha, fin)),
        )
        auditoria.registrar(
            persona,
            "cita.agendar",
            "Cita",
            cita.id,
            despues={"fecha": fecha.isoformat(), "hora_inicio": inicio, "hora_fin": fin},
        )
        return cita

    try:
        return bloqueo.tomar(crear)
    except bloqueo.RecursoOcupado as ocupado:
        if ocupado.restriccion == "cita_unica_por_persona":
            raise CitaActivaExistente() from ocupado
        if ocupado.restriccion == "cita_franja_activa":
            raise FranjaDeCitaOcupada() from ocupado
        raise


def horario_actual(conjunto_id):
    horario = HorarioDeAtencion.objects.filter(conjunto_id=conjunto_id).first()
    if horario is not None:
        return {"id": str(horario.id), "dias": horario.dias}
    return {"id": None, "dias": [
        {
            "dia": dia,
            "activo": False,
            "hora_inicio": None,
            "hora_fin": None,
            "descanso_inicio": None,
            "descanso_fin": None,
        }
        for dia in range(7)
    ]}


def guardar_horario(actor, conjunto_id, dias):
    """Guarda el horario semanal completo y deja el cambio en auditoría."""
    dias = [
        {
            **dia,
            "hora_inicio": dia["hora_inicio"].strftime("%H:%M") if dia["hora_inicio"] else None,
            "hora_fin": dia["hora_fin"].strftime("%H:%M") if dia["hora_fin"] else None,
            "descanso_inicio": dia["descanso_inicio"].strftime("%H:%M") if dia["descanso_inicio"] else None,
            "descanso_fin": dia["descanso_fin"].strftime("%H:%M") if dia["descanso_fin"] else None,
        }
        for dia in sorted(dias, key=lambda dia: dia["dia"])
    ]
    with transaction.atomic():
        Conjunto.objects.select_for_update().get(pk=conjunto_id)
        horario = HorarioDeAtencion.objects.filter(conjunto_id=conjunto_id).first()
        anterior = horario.dias if horario else None
        if horario is None:
            horario = HorarioDeAtencion.objects.create(
                conjunto_id=conjunto_id,
                dias=dias,
                actualizado_por=actor,
            )
        else:
            horario.dias = dias
            horario.actualizado_por = actor
            horario.save(update_fields=["dias", "actualizado_por", "actualizado_en"])
        auditoria.registrar(
            actor,
            "cita.horario.editar",
            "HorarioDeAtencion",
            horario.id,
            antes=anterior,
            despues=dias,
        )
    return {"id": str(horario.id), "dias": horario.dias}
