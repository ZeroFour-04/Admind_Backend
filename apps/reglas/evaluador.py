"""Motor de reglas de reserva (maestro §5.10, HU-13).

Evalúa todas las alfas y todas las beta vigentes del área, en AND y sin detenerse en la primera
falla: la persona ve todos los motivos a la vez. Como todas las reglas solo restringen, no hay
precedencias ni conflictos.

Se aplican las beta vigentes el día en que se evalúa: una solicitud decidida con la versión 1 de
una regla no cambia cuando entra la versión 2, y la copia de la versión queda en la solicitud.
"""
from datetime import datetime, timedelta

from django.utils import timezone

from apps.reglas import alfa, mora
from apps.reglas.alfa import Resultado
from apps.reglas.catalogo import TipoDeRegla, describir, lista_de_dias
from apps.reglas.servicios import reglas_vigentes
from apps.reservas.models import EstadoSolicitud, Solicitud


def anticipacion_minima(solicitud, p):
    inicio = timezone.make_aware(datetime.combine(solicitud.fecha, solicitud.hora_inicio))
    if inicio - timezone.now() >= timedelta(hours=p["horas"]):
        return ""
    return f"Esta área se solicita con al menos {p['horas']} horas de anticipación."


def anticipacion_maxima(solicitud, p):
    if solicitud.fecha <= timezone.localdate() + timedelta(days=p["dias"]):
        return ""
    return f"Esta área se solicita con máximo {p['dias']} días de anticipación."


def cupo_por_unidad(solicitud, p):
    """Cuenta las apartadas y reservadas de la unidad en esa área en los `dias` días que terminan en la franja."""
    desde = solicitud.fecha - timedelta(days=p["dias"] - 1)
    usadas = Solicitud.objects.filter(
        unidad_id=solicitud.unidad_id,
        area_id=solicitud.area_id,
        estado__in=[EstadoSolicitud.APARTADA, EstadoSolicitud.RESERVADA],
        fecha__range=(desde, solicitud.fecha),
    ).exclude(pk=solicitud.pk).count()
    if usadas < p["reservas"]:
        return ""
    return (
        f"Este apartamento ya tiene {usadas} reservas de esta área en {p['dias']} días; "
        f"el máximo es {p['reservas']}."
    )


def aforo(solicitud, p):
    if solicitud.asistentes <= p["maximo"]:
        return ""
    return f"Esta área admite máximo {p['maximo']} asistentes y la solicitud dice {solicitud.asistentes}."


def franja_horaria(solicitud, p):
    en_dia = solicitud.fecha.weekday() in p["dias_semana"]
    en_hora = solicitud.hora_inicio.strftime("%H:%M") >= p["desde"] and solicitud.hora_fin.strftime("%H:%M") <= p["hasta"]
    if en_dia and en_hora:
        return ""
    return f"Esta área solo se reserva los {lista_de_dias(p['dias_semana'])}, de {p['desde']} a {p['hasta']}."


def dias_no_reservables(solicitud, p):
    if solicitud.fecha.weekday() not in p["dias_semana"] and solicitud.fecha.isoformat() not in p["fechas"]:
        return ""
    return "Esta área no se reserva ese día."


def requiere_paz_y_salvo(solicitud, p):
    # La mora solo restringe áreas no esenciales (regla alfa, maestro §5.10).
    if solicitud.area.es_esencial or not mora.unidad_en_mora(solicitud.unidad):
        return ""
    return "El apartamento no está a paz y salvo con la administración."


# Un evaluador por tipo del catálogo. Cada uno devuelve el motivo si no cumple, o "" si cumple.
EVALUADOR_POR_TIPO = {
    TipoDeRegla.ANTICIPACION_MINIMA: anticipacion_minima,
    TipoDeRegla.ANTICIPACION_MAXIMA: anticipacion_maxima,
    TipoDeRegla.CUPO_POR_UNIDAD: cupo_por_unidad,
    TipoDeRegla.AFORO: aforo,
    TipoDeRegla.FRANJA_HORARIA: franja_horaria,
    TipoDeRegla.DIAS_NO_RESERVABLES: dias_no_reservables,
    TipoDeRegla.REQUIERE_PAZ_Y_SALVO: requiere_paz_y_salvo,
}


def evaluar(solicitud):
    """Todas las reglas, en AND. Devuelve un `Resultado` por regla, cumpla o no."""
    resultados = [regla_alfa(solicitud) for regla_alfa in alfa.ALFAS]
    for regla in reglas_vigentes(solicitud.area, timezone.localdate()):
        motivo = EVALUADOR_POR_TIPO[regla.tipo](solicitud, regla.parametros)
        resultados.append(
            Resultado(
                regla.tipo,
                describir(regla.tipo, regla.parametros),
                not motivo,
                motivo,
                regla_id=regla.id,
                parametros=regla.parametros,
            )
        )
    return resultados
