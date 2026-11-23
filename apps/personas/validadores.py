"""Formato de los datos de una persona al crearla. El front repite estas reglas para avisar mientras se
escribe (apps/usuarios/validacion.py del front); aquí está la que manda."""
import re

from rest_framework import serializers

from apps.personas.models import TipoDocumento, normalizar_documento

DOCUMENTO_MINIMO = 5
DOCUMENTO_MAXIMO = 11
# El pasaporte es el único documento colombiano que lleva letras.
TIPOS_CON_LETRAS = {TipoDocumento.PAS}

SOLO_DIGITOS = re.compile(r"^[0-9]+$")
SOLO_LETRAS_Y_DIGITOS = re.compile(r"^[A-Z0-9]+$")
SOLO_LETRAS = r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+(?:[ '-][A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+)*$"
PLACA = r"^[A-Za-z0-9]{5,7}$"

MENSAJE_DIGITOS = "En este campo solo se aceptan números, sin puntos ni espacios."
MENSAJE_LETRAS_Y_DIGITOS = "En este campo solo se aceptan letras y números, sin espacios ni símbolos."
MENSAJE_LETRAS = "En este campo solo se aceptan letras y espacios."
MENSAJE_PLACA = "La placa solo acepta letras y números, sin espacios ni guiones (5 a 7 caracteres)."
MENSAJE_LARGO_DOCUMENTO = f"El documento debe tener entre {DOCUMENTO_MINIMO} y {DOCUMENTO_MAXIMO} caracteres."


def validar_documento(tipo, numero):
    """Devuelve el número normalizado o lanza ValidationError. Los puntos y espacios se quitan antes."""
    normalizado = normalizar_documento(numero)
    if tipo in TIPOS_CON_LETRAS:
        patron, mensaje = SOLO_LETRAS_Y_DIGITOS, MENSAJE_LETRAS_Y_DIGITOS
    else:
        patron, mensaje = SOLO_DIGITOS, MENSAJE_DIGITOS
    if not patron.match(normalizado):
        raise serializers.ValidationError(mensaje)
    if not DOCUMENTO_MINIMO <= len(normalizado) <= DOCUMENTO_MAXIMO:
        raise serializers.ValidationError(MENSAJE_LARGO_DOCUMENTO)
    return normalizado


def campo_letras(max_length, **kwargs):
    """Nombres y apellidos: letras (con tildes y ñ), espacios, guion y apóstrofo."""
    return serializers.RegexField(
        regex=SOLO_LETRAS,
        min_length=2,
        max_length=max_length,
        error_messages={"invalid": MENSAJE_LETRAS, "min_length": "Escribe al menos 2 letras."},
        **kwargs,
    )


def campo_cedula():
    return serializers.RegexField(
        regex=r"^[0-9]+$",
        min_length=DOCUMENTO_MINIMO,
        max_length=DOCUMENTO_MAXIMO,
        error_messages={
            "invalid": MENSAJE_DIGITOS,
            "min_length": MENSAJE_LARGO_DOCUMENTO,
            "max_length": MENSAJE_LARGO_DOCUMENTO,
        },
    )


def campo_placa(**kwargs):
    return serializers.RegexField(regex=PLACA, max_length=7, error_messages={"invalid": MENSAJE_PLACA}, **kwargs)
