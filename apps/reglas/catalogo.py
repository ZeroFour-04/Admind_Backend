"""Catálogo cerrado de tipos de regla beta (maestro §5.10, HU-10, plan D4 a).

Provisional hasta validarlo contra un reglamento real (maestro §11.4). Todos los tipos
restringen: no existe ninguno que permita algo, así que se evalúan en AND sin conflictos.

Los días de la semana van de 0 (lunes) a 6 (domingo), como `date.weekday()`.
"""
from datetime import date, time

from django.db import models


class TipoDeRegla(models.TextChoices):
    ANTICIPACION_MINIMA = "ANTICIPACION_MINIMA", "Anticipación mínima"
    ANTICIPACION_MAXIMA = "ANTICIPACION_MAXIMA", "Anticipación máxima"
    CUPO_POR_UNIDAD = "CUPO_POR_UNIDAD", "Cupo por apartamento"
    AFORO = "AFORO", "Aforo"
    FRANJA_HORARIA = "FRANJA_HORARIA", "Franja horaria"
    DIAS_NO_RESERVABLES = "DIAS_NO_RESERVABLES", "Días no reservables"
    REQUIERE_PAZ_Y_SALVO = "REQUIERE_PAZ_Y_SALVO", "Requiere paz y salvo"


# En plural, como se dicen en una regla: «los sábados».
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábados", "domingos"]


class ParametrosInvalidos(Exception):
    """Los parámetros no sirven para ese tipo. Trae los mensajes por campo."""

    def __init__(self, errores):
        super().__init__(errores)
        self.errores = errores


# Validación de cada parámetro. Devuelven el valor normalizado o lanzan ValueError con el mensaje.


def entero(minimo):
    def validar(valor):
        if isinstance(valor, bool) or not isinstance(valor, int):
            raise ValueError("Debe ser un número entero.")
        if valor < minimo:
            raise ValueError(f"Debe ser mayor o igual a {minimo}.")
        return valor

    return validar


def hora(valor):
    try:
        return time.fromisoformat(valor).strftime("%H:%M")
    except (TypeError, ValueError):
        raise ValueError("Debe ser una hora con el formato HH:MM.") from None


def dias_de_la_semana(valor):
    if not isinstance(valor, list) or any(isinstance(d, bool) or not isinstance(d, int) or not 0 <= d <= 6 for d in valor):
        raise ValueError("Debe ser una lista de días de 0 (lunes) a 6 (domingo).")
    return sorted(set(valor))


def fechas(valor):
    try:
        return sorted({date.fromisoformat(fecha).isoformat() for fecha in valor})
    except (TypeError, ValueError):
        raise ValueError("Debe ser una lista de fechas con el formato AAAA-MM-DD.") from None


# Qué parámetros lleva cada tipo. Ni uno de más ni uno de menos.
PARAMETROS_POR_TIPO = {
    # Menos de 0 relajaría la alfa «no se reserva en el pasado».
    TipoDeRegla.ANTICIPACION_MINIMA: {"horas": entero(0)},
    TipoDeRegla.ANTICIPACION_MAXIMA: {"dias": entero(1)},
    TipoDeRegla.CUPO_POR_UNIDAD: {"reservas": entero(1), "dias": entero(1)},
    TipoDeRegla.AFORO: {"maximo": entero(1)},
    TipoDeRegla.FRANJA_HORARIA: {"dias_semana": dias_de_la_semana, "desde": hora, "hasta": hora},
    TipoDeRegla.DIAS_NO_RESERVABLES: {"dias_semana": dias_de_la_semana, "fechas": fechas},
    TipoDeRegla.REQUIERE_PAZ_Y_SALVO: {},
}


def validar(tipo, parametros, area):
    """Los parámetros normalizados, o `ParametrosInvalidos`. Una regla beta nunca relaja una alfa."""
    if not isinstance(parametros, dict):
        raise ParametrosInvalidos({"parametros": ["Deben ser un objeto con los parámetros del tipo."]})
    esperados = PARAMETROS_POR_TIPO[tipo]
    errores = {}
    for sobrante in sorted(set(parametros) - set(esperados)):
        errores[sobrante] = ["Este tipo de regla no lleva este parámetro."]
    normalizados = {}
    for nombre, validar_parametro in esperados.items():
        if nombre not in parametros:
            errores[nombre] = ["Este parámetro es obligatorio."]
            continue
        try:
            normalizados[nombre] = validar_parametro(parametros[nombre])
        except ValueError as error:
            errores[nombre] = [str(error)]
    if errores:
        raise ParametrosInvalidos(errores)

    if tipo == TipoDeRegla.FRANJA_HORARIA:
        if not normalizados["dias_semana"]:
            errores["dias_semana"] = ["Elige al menos un día."]
        if normalizados["desde"] >= normalizados["hasta"]:
            errores["hasta"] = ["La hora final debe ser posterior a la inicial."]
    if tipo == TipoDeRegla.DIAS_NO_RESERVABLES and not normalizados["dias_semana"] and not normalizados["fechas"]:
        errores["parametros"] = ["Indica al menos un día de la semana o una fecha."]
    if tipo == TipoDeRegla.REQUIERE_PAZ_Y_SALVO and area.es_esencial:
        # Regla alfa: la mora solo restringe áreas no esenciales (maestro §5.10).
        errores["parametros"] = ["Un área común esencial no se puede restringir por mora."]
    if errores:
        raise ParametrosInvalidos(errores)
    return normalizados


def lista_de_dias(dias):
    nombres = [DIAS[dia] for dia in dias]
    return nombres[0] if len(nombres) == 1 else f"{', '.join(nombres[:-1])} y {nombres[-1]}"


def describir(tipo, p):
    """La regla en palabras, para la pantalla. Por ejemplo: «Máximo 25 asistentes»."""
    if tipo == TipoDeRegla.ANTICIPACION_MINIMA:
        return f"Se solicita con al menos {p['horas']} horas de anticipación"
    if tipo == TipoDeRegla.ANTICIPACION_MAXIMA:
        return f"Se solicita con máximo {p['dias']} días de anticipación"
    if tipo == TipoDeRegla.CUPO_POR_UNIDAD:
        return f"Máximo {p['reservas']} reservas por apartamento cada {p['dias']} días"
    if tipo == TipoDeRegla.AFORO:
        return f"Máximo {p['maximo']} asistentes"
    if tipo == TipoDeRegla.FRANJA_HORARIA:
        return f"Solo los {lista_de_dias(p['dias_semana'])}, de {p['desde']} a {p['hasta']}"
    if tipo == TipoDeRegla.DIAS_NO_RESERVABLES:
        partes = []
        if p["dias_semana"]:
            partes.append(f"los {lista_de_dias(p['dias_semana'])}")
        if p["fechas"]:
            partes.append(f"el {', '.join(p['fechas'])}")
        return f"No se reserva {' ni '.join(partes)}"
    return "Requiere estar a paz y salvo con la administración"
