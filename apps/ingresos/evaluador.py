"""Reglas de un ingreso a una zona (plan P14). Mismo criterio que `reglas/evaluador.py`: todas en AND y
sin detenerse en la primera falla, así quien registra ve todos los motivos a la vez.

Orden: reglas del sistema, aforo, y las reglas del conjunto y del área que aplican al ingreso.
`reglas` no importa esta app: aquí se reutilizan su `Resultado`, su catálogo y sus reglas vigentes.
"""
from django.db.models import Sum
from django.utils import timezone

from apps.areas.models import ModoDeUso
from apps.ingresos.models import EstadoIngreso, Ingreso
from apps.reglas import mora
from apps.reglas.catalogo import (
    MODO_INGRESO,
    MODOS_POR_TIPO,
    NIVEL_POR_TIPO,
    Nivel,
    TipoDeRegla,
    describir,
    motivos_del_dia,
)
from apps.reglas.servicios import reglas_vigentes
from apps.reglas.sistema import Resultado
from apps.unidades.models import VinculoUnidad


def reside(ingreso):
    cumple = VinculoUnidad.objects.vigentes().filter(
        persona_id=ingreso.persona_id, unidad_id=ingreso.unidad_id, reside=True
    ).exists()
    return Resultado(
        "RESIDE",
        "Solo ingresa quien vive en la vivienda elegida",
        cumple,
        "" if cumple else "La persona no vive en la vivienda elegida.",
    )


def area_disponible(ingreso):
    area = ingreso.area
    cumple = area.activo and not area.en_mantenimiento and area.modo_uso == ModoDeUso.INGRESO
    return Resultado(
        "AREA_DISPONIBLE",
        "La zona es con ingreso, está activa y no está en mantenimiento",
        cumple,
        "" if cumple else "Esta zona no está disponible para ingresos en este momento.",
    )


def dentro_del_horario(ingreso):
    area = ingreso.area
    hora = timezone.localtime(ingreso.entrada_en).time()
    cumple = area.hora_apertura <= hora < area.hora_cierre
    return Resultado(
        "DENTRO_DEL_HORARIO",
        f"Solo se ingresa de {area.hora_apertura:%H:%M} a {area.hora_cierre:%H:%M}",
        cumple,
        "" if cumple else f"La zona atiende de {area.hora_apertura:%H:%M} a {area.hora_cierre:%H:%M}.",
    )


def sin_otro_ingreso_abierto(ingreso):
    cumple = not Ingreso.objects.filter(persona_id=ingreso.persona_id, estado=EstadoIngreso.ADENTRO).exists()
    return Resultado(
        "UN_INGRESO_ABIERTO",
        "Una persona tiene un solo ingreso abierto a la vez",
        cumple,
        "" if cumple else "La persona ya está adentro de una zona.",
    )


REGLAS_DEL_SISTEMA = [reside, area_disponible, dentro_del_horario, sin_otro_ingreso_abierto]


def aforo(ingreso, ocupacion):
    """Los que ya están adentro, más la persona y sus acompañantes, no superan el aforo."""
    maximo = ingreso.area.aforo_maximo
    entran = 1 + ingreso.acompanantes
    cumple = ocupacion + entran <= maximo
    libres = max(0, maximo - ocupacion)
    motivo = "" if cumple else f"Entran {entran} y en esta zona quedan {libres} puestos libres de {maximo}."
    return Resultado(
        "AFORO", f"Máximo {maximo} personas adentro", cumple, motivo, parametros={"maximo": maximo}, nivel=Nivel.BETA.value
    )


def acompanantes(ingreso, p):
    """Los de esa vivienda que ya están adentro, más los que entran, no pasan del máximo."""
    adentro = (
        Ingreso.objects.filter(unidad_id=ingreso.unidad_id, estado=EstadoIngreso.ADENTRO).aggregate(
            total=Sum("acompanantes")
        )["total"]
        or 0
    )
    if ingreso.acompanantes == 0 or adentro + ingreso.acompanantes <= p["maximo"]:
        return ""
    if p["maximo"] == 0:
        return "En este conjunto no se permiten acompañantes."
    return (
        f"Esta vivienda ya tiene {adentro} acompañantes adentro y el máximo es {p['maximo']}; "
        f"con {ingreso.acompanantes} más lo supera."
    )


def dias_que_no_abre(ingreso, p):
    motivos = motivos_del_dia(timezone.localtime(ingreso.entrada_en).date(), p["renglones"])
    if not motivos:
        return ""
    return f"Esta zona no abre hoy: {'; '.join(motivos)}."


def requiere_paz_y_salvo(ingreso, p):
    if not mora.unidad_en_mora(ingreso.unidad):
        return ""
    return "La vivienda no está a paz y salvo con la administración."


EVALUADOR_POR_TIPO = {
    TipoDeRegla.ACOMPANANTES: acompanantes,
    TipoDeRegla.DIAS_QUE_NO_ABRE: dias_que_no_abre,
    TipoDeRegla.REQUIERE_PAZ_Y_SALVO: requiere_paz_y_salvo,
}


def evaluar(ingreso, ocupacion):
    """Un `Resultado` por regla, cumpla o no. `ocupacion` son las personas que ya están adentro del área."""
    resultados = [regla(ingreso) for regla in REGLAS_DEL_SISTEMA]
    resultados.append(aforo(ingreso, ocupacion))
    hoy = timezone.localtime(ingreso.entrada_en).date()
    for regla in reglas_vigentes(ingreso.area, hoy):
        if MODO_INGRESO not in MODOS_POR_TIPO.get(regla.tipo, []):
            continue
        evaluar_tipo = EVALUADOR_POR_TIPO[regla.tipo]
        motivo = evaluar_tipo(ingreso, regla.parametros)
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
