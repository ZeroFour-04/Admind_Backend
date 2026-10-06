"""Motor de reglas de reserva (definición del 2026-10-06, HU-13).

Evalúa, en este orden, las reglas del sistema, el aforo del área, las reglas del conjunto (alfa) y
las del área (beta). Todas en AND y sin detenerse en la primera falla: la persona ve todos los
motivos a la vez. Como todas las reglas solo restringen, no hay precedencias ni conflictos.

Se aplican las reglas vigentes el día en que se evalúa: una solicitud decidida con la versión 1 de
una regla no cambia cuando entra la versión 2, y la copia de la versión queda en la solicitud.
"""
from datetime import datetime, timedelta

from django.utils import timezone

from apps.reglas import mora, sistema
from apps.reglas.catalogo import NIVEL_POR_TIPO, Nivel, TipoDeRegla, describir, motivos_del_dia
from apps.reglas.servicios import reglas_vigentes
from apps.reglas.sistema import Resultado
from apps.reservas.models import EstadoSolicitud, Solicitud


def aforo(solicitud):
    """El aforo es un dato del área y se evalúa siempre (P8)."""
    maximo = solicitud.area.aforo_maximo
    cumple = solicitud.asistentes <= maximo
    motivo = "" if cumple else f"Esta área admite máximo {maximo} asistentes y la solicitud dice {solicitud.asistentes}."
    return Resultado(
        "AFORO", f"Máximo {maximo} asistentes", cumple, motivo, parametros={"maximo": maximo}, nivel=Nivel.BETA.value
    )


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


def dias_que_no_abre(solicitud, p):
    motivos = motivos_del_dia(solicitud.fecha, p["renglones"])
    if not motivos:
        return ""
    return f"Esta área no abre ese día: {'; '.join(motivos)}."


def requiere_paz_y_salvo(solicitud, p):
    if not mora.unidad_en_mora(solicitud.unidad):
        return ""
    return "El apartamento no está a paz y salvo con la administración."


# Un evaluador por tipo vigente. Cada uno devuelve el motivo si no cumple, o "" si cumple.
EVALUADOR_POR_TIPO = {
    TipoDeRegla.ANTICIPACION_MINIMA: anticipacion_minima,
    TipoDeRegla.ANTICIPACION_MAXIMA: anticipacion_maxima,
    TipoDeRegla.REQUIERE_PAZ_Y_SALVO: requiere_paz_y_salvo,
    TipoDeRegla.DIAS_QUE_NO_ABRE: dias_que_no_abre,
    TipoDeRegla.CUPO_POR_UNIDAD: cupo_por_unidad,
}


def evaluar(solicitud):
    """Todas las reglas, en AND: sistema, aforo, del conjunto y del área. Un `Resultado` por regla, cumpla o no."""
    resultados = [regla(solicitud) for regla in sistema.REGLAS_DEL_SISTEMA]
    resultados.append(aforo(solicitud))
    for regla in reglas_vigentes(solicitud.area, timezone.localdate()):
        evaluar_tipo = EVALUADOR_POR_TIPO.get(regla.tipo)
        if evaluar_tipo is None:
            # Una regla que se define pero todavía no tiene quién la evalúe (solo con D3 = b).
            continue
        motivo = evaluar_tipo(solicitud, regla.parametros)
        resultados.append(
            Resultado(
                regla.tipo,
                describir(regla.tipo, regla.parametros),
                not motivo,
                motivo,
                regla_id=regla.id,
                parametros=regla.parametros,
                nivel=NIVEL_POR_TIPO[regla.tipo].value,
            )
        )
    return resultados
