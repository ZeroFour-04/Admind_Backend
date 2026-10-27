"""Catálogo cerrado de reglas de reserva, por niveles (definición del 2026-10-06, HU-10).

El 2026-10-10 entraron dos reglas de área sin parámetros: una reserva al día y sin franjas seguidas, y
el día límite de pago, que ningún evaluador evalúa: la lee `pagos` para calcular la mora (HU-35).

Una regla alfa es del conjunto y vale para todas sus áreas; una beta es de un área. Cada tipo
vive en un solo nivel y se define una sola vez. Todos restringen: no existe ninguno que permita
algo, así que se evalúan en AND sin conflictos. Los tipos retirados quedan para leer el historial.

Los días de la semana van de 0 (lunes) a 6 (domingo), como `date.weekday()`.
"""
from datetime import date

from django.db import models
from django.utils.formats import date_format


class Nivel(models.TextChoices):
    ALFA = "alfa", "Del conjunto"
    BETA = "beta", "Del área"


class TipoDeRegla(models.TextChoices):
    ANTICIPACION_MINIMA = "ANTICIPACION_MINIMA", "Anticipación mínima"
    ANTICIPACION_MAXIMA = "ANTICIPACION_MAXIMA", "Anticipación máxima"
    REQUIERE_PAZ_Y_SALVO = "REQUIERE_PAZ_Y_SALVO", "Paz y salvo"
    DIA_LIMITE_DE_PAGO = "DIA_LIMITE_DE_PAGO", "Día límite de pago"
    DIAS_QUE_NO_ABRE = "DIAS_QUE_NO_ABRE", "Días que no abre"
    CUPO_POR_UNIDAD = "CUPO_POR_UNIDAD", "Límite de reservas por apartamento"
    ACOMPANANTES = "ACOMPANANTES", "Acompañantes"
    UNA_RESERVA_POR_DIA = "UNA_RESERVA_POR_DIA", "Una reserva al día"
    SIN_FRANJAS_SEGUIDAS = "SIN_FRANJAS_SEGUIDAS", "Sin franjas seguidas"
    PARQUEADEROS_POR_VIVIENDA = "PARQUEADEROS_POR_VIVIENDA", "Parqueaderos por vivienda"
    # Retirados el 2026-10-06. Quedan para leer el historial: no se crean ni se editan.
    AFORO = "AFORO", "Aforo"
    FRANJA_HORARIA = "FRANJA_HORARIA", "Franja horaria"
    DIAS_NO_RESERVABLES = "DIAS_NO_RESERVABLES", "Días no reservables"


# En qué nivel vive cada tipo que se puede definir hoy. Un tipo que no está aquí está retirado.
NIVEL_POR_TIPO = {
    TipoDeRegla.ANTICIPACION_MINIMA: Nivel.ALFA,
    TipoDeRegla.ANTICIPACION_MAXIMA: Nivel.ALFA,
    TipoDeRegla.REQUIERE_PAZ_Y_SALVO: Nivel.ALFA,
    TipoDeRegla.DIA_LIMITE_DE_PAGO: Nivel.ALFA,
    TipoDeRegla.ACOMPANANTES: Nivel.ALFA,
    TipoDeRegla.PARQUEADEROS_POR_VIVIENDA: Nivel.ALFA,
    TipoDeRegla.DIAS_QUE_NO_ABRE: Nivel.BETA,
    TipoDeRegla.CUPO_POR_UNIDAD: Nivel.BETA,
    TipoDeRegla.UNA_RESERVA_POR_DIA: Nivel.BETA,
    TipoDeRegla.SIN_FRANJAS_SEGUIDAS: Nivel.BETA,
}
# A qué modo de uso del área aplica cada tipo vigente (plan P5). Una regla de área solo se define en un área de sus modos.
MODO_RESERVA, MODO_INGRESO = "reserva", "ingreso"
MODOS_POR_TIPO = {
    TipoDeRegla.ANTICIPACION_MINIMA: [MODO_RESERVA],
    TipoDeRegla.ANTICIPACION_MAXIMA: [MODO_RESERVA],
    TipoDeRegla.REQUIERE_PAZ_Y_SALVO: [MODO_RESERVA, MODO_INGRESO],
    # Ningún modo: no restringe por sí sola, la lee `pagos` para saber desde cuándo hay mora.
    TipoDeRegla.DIA_LIMITE_DE_PAGO: [],
    TipoDeRegla.ACOMPANANTES: [MODO_INGRESO],
    # Ningún modo: ningún evaluador de reservas ni de ingresos la toca, la lee la asignación de parqueaderos (HU-34).
    TipoDeRegla.PARQUEADEROS_POR_VIVIENDA: [],
    TipoDeRegla.DIAS_QUE_NO_ABRE: [MODO_RESERVA, MODO_INGRESO],
    TipoDeRegla.CUPO_POR_UNIDAD: [MODO_RESERVA],
    TipoDeRegla.UNA_RESERVA_POR_DIA: [MODO_RESERVA],
    TipoDeRegla.SIN_FRANJAS_SEGUIDAS: [MODO_RESERVA],
}
# Como texto, porque van dentro de una restricción de la base (F3).
TIPOS_ALFA = [tipo.value for tipo, nivel in NIVEL_POR_TIPO.items() if nivel == Nivel.ALFA]
TIPOS_BETA = [tipo.value for tipo, nivel in NIVEL_POR_TIPO.items() if nivel == Nivel.BETA]

# Lo que lee Administración junto a cada regla. La escribe el sistema, no quien configura.
DESCRIPCION_POR_TIPO = {
    TipoDeRegla.ANTICIPACION_MINIMA: (
        "Cuántas horas antes, como mínimo, se pide una reserva. Con 24, nadie reserva para hoy mismo. "
        "Con 0 no hay mínimo."
    ),
    TipoDeRegla.ANTICIPACION_MAXIMA: (
        "Hasta cuántos días hacia adelante se puede reservar. Con 30, hoy se puede pedir cualquier fecha "
        "de los próximos 30 días y ninguna posterior."
    ),
    TipoDeRegla.REQUIERE_PAZ_Y_SALVO: (
        "Si la activas, un apartamento en mora con la administración no reserva ni ingresa a las zonas comunes "
        "hasta ponerse al día. Aplícala solo si el reglamento del conjunto lo permite."
    ),
    TipoDeRegla.DIA_LIMITE_DE_PAGO: (
        "El día del mes hasta el que se paga la administración sin entrar en mora. Con 10, quien no tenga el "
        "pago confirmado el 11 queda en mora."
    ),
    TipoDeRegla.ACOMPANANTES: (
        "Cuántos acompañantes puede tener adentro una misma vivienda a la vez, en las áreas con ingreso. Con 2, "
        "una vivienda tiene como máximo 2 acompañantes dentro al mismo tiempo. Con 0 no se permiten. Cada "
        "acompañante ocupa un puesto del aforo."
    ),
    TipoDeRegla.PARQUEADEROS_POR_VIVIENDA: (
        "Cuántos parqueaderos de residentes puede tener asignados una misma vivienda, por tipo de vehículo. "
        "Con carro 1, moto 1 y bicicleta 0, una vivienda tiene un puesto de carro, uno de moto y ninguno de "
        "bicicleta. Sin esta regla no hay tope. Solo limita las asignaciones nuevas."
    ),
    TipoDeRegla.DIAS_QUE_NO_ABRE: (
        "Días de la semana, fechas o periodos en que el área no presta servicio. Cada uno lleva su motivo, "
        "que es lo que lee el residente."
    ),
    TipoDeRegla.CUPO_POR_UNIDAD: (
        "Cuántas reservas de esta área puede tener un mismo apartamento en un periodo. Con 2 cada 30 días, "
        "un apartamento no aparta el salón todos los fines de semana."
    ),
    TipoDeRegla.UNA_RESERVA_POR_DIA: (
        "Si la activas, el área admite una sola reserva por día: cuando una franja queda apartada o reservada, "
        "las demás de ese día dejan de ofrecerse. Sirve para un salón comunal. Sin esta regla, cada franja se "
        "reserva por separado."
    ),
    TipoDeRegla.SIN_FRANJAS_SEGUIDAS: (
        "Si la activas, un mismo apartamento no reserva dos franjas seguidas del mismo día en esta área. Con "
        "franjas de 8:00 a 12:00 y de 12:00 a 16:00, quien tiene la primera no toma la segunda. Sin esta regla, "
        "puede encadenarlas."
    ),
}
# Lo que Administración tiene que saber de una regla antes de definirla.
NOTA_POR_TIPO = {
    TipoDeRegla.REQUIERE_PAZ_Y_SALVO: "Solo restringe si también defines el día límite de pago.",
}


def tipos_vigentes():
    """El catálogo que se muestra: una entrada por tipo que se puede definir, primero las del conjunto."""
    return [
        {
            "tipo": tipo.value,
            "nivel": nivel.value,
            "nombre": tipo.label,
            "modos": MODOS_POR_TIPO[tipo],
            "descripcion": DESCRIPCION_POR_TIPO[tipo],
            "nota": NOTA_POR_TIPO.get(tipo, ""),
        }
        for tipo, nivel in NIVEL_POR_TIPO.items()
    ]


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


def entero_entre(minimo, maximo):
    """Un entero de `minimo` a `maximo`, ambos incluidos."""
    desde_el_minimo = entero(minimo)

    def validar(valor):
        valor = desde_el_minimo(valor)
        if valor > maximo:
            raise ValueError(f"Debe ser menor o igual a {maximo}.")
        return valor

    return validar


MAXIMO_DE_RENGLONES = 60
LARGO_DEL_MOTIVO = 120
RENGLON_MAL_ARMADO = "Cada renglón lleva un día de la semana o un periodo, y su motivo."


def renglones(valor):
    """Los días que no abre: cada renglón es un día de la semana o un periodo, siempre con motivo (P4)."""
    if not isinstance(valor, list) or not valor:
        raise ValueError("Agrega al menos un día que no abre.")
    if len(valor) > MAXIMO_DE_RENGLONES:
        raise ValueError(f"Máximo {MAXIMO_DE_RENGLONES} renglones.")
    dias, periodos = {}, []
    for renglon in valor:
        if not isinstance(renglon, dict):
            raise ValueError(RENGLON_MAL_ARMADO)
        motivo = renglon.get("motivo")
        if not isinstance(motivo, str) or not motivo.strip():
            raise ValueError("Cada día que no abre lleva su motivo.")
        motivo = motivo.strip()
        if len(motivo) > LARGO_DEL_MOTIVO:
            raise ValueError(f"El motivo no puede pasar de {LARGO_DEL_MOTIVO} caracteres.")
        if set(renglon) == {"dia_semana", "motivo"}:
            dia = renglon["dia_semana"]
            if isinstance(dia, bool) or not isinstance(dia, int) or not 0 <= dia <= 6:
                raise ValueError("El día de la semana va de 0 (lunes) a 6 (domingo).")
            if dia in dias:
                raise ValueError(f"Los {DIAS[dia]} ya están en la lista.")
            dias[dia] = motivo
        elif set(renglon) == {"desde", "hasta", "motivo"}:
            try:
                desde, hasta = date.fromisoformat(renglon["desde"]), date.fromisoformat(renglon["hasta"])
            except (TypeError, ValueError):
                raise ValueError("Las fechas van con el formato AAAA-MM-DD.") from None
            if hasta < desde:
                raise ValueError("La fecha final no puede ser anterior a la inicial.")
            periodos.append((desde, hasta, motivo))
        else:
            raise ValueError(RENGLON_MAL_ARMADO)
    return [{"dia_semana": dia, "motivo": dias[dia]} for dia in sorted(dias)] + [
        {"desde": desde.isoformat(), "hasta": hasta.isoformat(), "motivo": motivo}
        for desde, hasta, motivo in sorted(periodos)
    ]


# Qué parámetros lleva cada tipo vigente. Ni uno de más ni uno de menos.
PARAMETROS_POR_TIPO = {
    # Menos de 0 relajaría la regla del sistema «no se reserva en el pasado».
    TipoDeRegla.ANTICIPACION_MINIMA: {"horas": entero(0)},
    TipoDeRegla.ANTICIPACION_MAXIMA: {"dias": entero(1)},
    TipoDeRegla.REQUIERE_PAZ_Y_SALVO: {},
    # Hasta el 28, para que el día exista en todos los meses.
    TipoDeRegla.DIA_LIMITE_DE_PAGO: {"dia": entero_entre(1, 28)},
    TipoDeRegla.DIAS_QUE_NO_ABRE: {"renglones": renglones},
    TipoDeRegla.CUPO_POR_UNIDAD: {"reservas": entero(1), "dias": entero(1)},
    # 0 es «no se permiten»: así la regla, como todas, solo restringe (plan D8 a).
    TipoDeRegla.ACOMPANANTES: {"maximo": entero(0)},
    # Sin parámetros: definirlas es activarlas. Sin definir, el área sigue como estaba; así solo restringen.
    TipoDeRegla.UNA_RESERVA_POR_DIA: {},
    TipoDeRegla.SIN_FRANJAS_SEGUIDAS: {},
    # Con 0 no se asigna ningún puesto de ese vehículo: así la regla, como todas, solo restringe.
    TipoDeRegla.PARQUEADEROS_POR_VIVIENDA: {"carro": entero(0), "moto": entero(0), "bicicleta": entero(0)},
}


def validar(tipo, parametros):
    """Los parámetros normalizados, o `ParametrosInvalidos`."""
    if tipo not in PARAMETROS_POR_TIPO:
        raise ParametrosInvalidos({"tipo": ["Este tipo de regla ya no se usa."]})
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
    return normalizados


def lista_de_dias(dias):
    nombres = [DIAS[dia] for dia in dias]
    return nombres[0] if len(nombres) == 1 else f"{', '.join(nombres[:-1])} y {nombres[-1]}"


def en_letras(fecha):
    # Django escribe «Diciembre»: se pasa a minúscula, como hace `dia_en_letras` en reservas.
    return date_format(fecha, r"j \d\e F \d\e Y").lower()


def describir_renglon(renglon):
    if "dia_semana" in renglon:
        return f"los {DIAS[renglon['dia_semana']]} ({renglon['motivo']})"
    desde, hasta = date.fromisoformat(renglon["desde"]), date.fromisoformat(renglon["hasta"])
    if desde == hasta:
        return f"el {en_letras(desde)} ({renglon['motivo']})"
    return f"del {en_letras(desde)} al {en_letras(hasta)} ({renglon['motivo']})"


def motivos_del_dia(fecha, renglones):
    """Los motivos por los que el área no abre ese día. Vacío si abre."""
    return [
        renglon["motivo"]
        for renglon in renglones
        if renglon.get("dia_semana") == fecha.weekday()
        or ("desde" in renglon and renglon["desde"] <= fecha.isoformat() <= renglon["hasta"])
    ]


def describir(tipo, p):
    """La regla en palabras, para la pantalla. Por ejemplo: «Máximo 25 asistentes»."""
    if tipo == TipoDeRegla.ANTICIPACION_MINIMA:
        return f"Se solicita con al menos {p['horas']} horas de anticipación"
    if tipo == TipoDeRegla.ANTICIPACION_MAXIMA:
        return f"Se solicita con máximo {p['dias']} días de anticipación"
    if tipo == TipoDeRegla.CUPO_POR_UNIDAD:
        return f"Máximo {p['reservas']} reservas por apartamento cada {p['dias']} días"
    if tipo == TipoDeRegla.ACOMPANANTES:
        if p["maximo"] == 0:
            return "No se permiten acompañantes"
        return f"Máximo {p['maximo']} {'acompañante' if p['maximo'] == 1 else 'acompañantes'} por vivienda a la vez"
    if tipo == TipoDeRegla.DIA_LIMITE_DE_PAGO:
        return f"La administración se paga hasta el día {p['dia']} de cada mes"
    if tipo == TipoDeRegla.PARQUEADEROS_POR_VIVIENDA:
        return f"Máximo {p['carro']} de carro, {p['moto']} de moto y {p['bicicleta']} de bicicleta por vivienda"
    if tipo == TipoDeRegla.UNA_RESERVA_POR_DIA:
        return "Solo una reserva al día"
    if tipo == TipoDeRegla.SIN_FRANJAS_SEGUIDAS:
        return "Un apartamento no reserva franjas seguidas"
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
    if tipo == TipoDeRegla.DIAS_QUE_NO_ABRE:
        return f"No abre {'; '.join(describir_renglon(renglon) for renglon in p['renglones'])}"
    return "Requiere estar a paz y salvo con la administración"
