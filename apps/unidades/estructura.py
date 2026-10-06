"""Generador de la estructura de viviendas (HU-39). Funciones puras: no tocan la base ni saben de HTTP.

Reciben lo que el administrador describió («6 torres de 10 pisos con 4 apartamentos por piso»)
y devuelven las viviendas que eso produce, con el nombre ya armado. Guardarlas es del servicio.
"""
import unicodedata
from dataclasses import dataclass

from django.db import models

ABREVIATURAS = {"apartamento": "Apto", "casa": "Casa"}


class Patron(models.TextChoices):
    PISO_CONSECUTIVO = "piso_consecutivo", "Piso y consecutivo"
    CONSECUTIVO = "consecutivo", "Consecutivo en cada agrupación"
    CORRIDO = "corrido", "Consecutivo corrido"
    LISTA = "lista", "Lista propia"


def limpiar(texto):
    """Sin espacios sobrantes y con la primera letra en mayúscula: «  torre » queda «Torre»."""
    texto = " ".join(texto.split())
    return texto[:1].upper() + texto[1:]


def clave(texto):
    """Para comparar: sin tildes ni mayúsculas. «Torre Ágata» y «torre agata» son la misma."""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(sin_tildes.lower().split())


def numeros_por_piso(pisos, por_piso, primer_piso=1):
    """101, 102 … 1004: el piso y, en dos cifras, el consecutivo dentro del piso."""
    return [
        (f"{piso}{consecutivo:02d}", piso)
        for piso in range(primer_piso, primer_piso + pisos)
        for consecutivo in range(1, por_piso + 1)
    ]


def numeros_consecutivos(cantidad, desde=1):
    return [(str(numero), None) for numero in range(desde, desde + cantidad)]


@dataclass(frozen=True)
class ViviendaPropuesta:
    numero: str
    piso: int | None
    nombre: str  # «Torre 1 – Apto 101»


@dataclass(frozen=True)
class AgrupacionPropuesta:
    etiqueta: str  # «Torre», o vacío si las viviendas no se agrupan
    nombre: str  # «1», «Esmeralda», «C»
    viviendas: tuple

    @property
    def nombre_completo(self):
        return f"{self.etiqueta} {self.nombre}".strip()


def nombre_de_vivienda(tipo_vivienda, agrupacion, numero):
    """«Torre 1 – Apto 101»; sin agrupación, «Casa 12»."""
    propio = f"{ABREVIATURAS[tipo_vivienda]} {numero}"
    return f"{agrupacion} – {propio}" if agrupacion else propio


def generar(descripcion):
    """De la descripción de una tanda a sus viviendas. `descripcion` es el diccionario ya validado."""
    tipo = descripcion["tipo_vivienda"]
    etiqueta = limpiar(descripcion.get("etiqueta", ""))
    patron = descripcion["patron"]
    siguiente = descripcion.get("desde", 1)
    propuestas = []
    for pedida in descripcion["agrupaciones"]:
        nombre = limpiar(pedida.get("nombre", ""))
        completo = f"{etiqueta} {nombre}".strip()
        if patron == Patron.PISO_CONSECUTIVO:
            numeros = numeros_por_piso(pedida["pisos"], pedida["por_piso"], descripcion.get("primer_piso", 1))
        elif patron == Patron.CONSECUTIVO:
            numeros = numeros_consecutivos(pedida["cantidad"])
        elif patron == Patron.CORRIDO:
            numeros = numeros_consecutivos(pedida["cantidad"], siguiente)
            siguiente += pedida["cantidad"]
        else:
            numeros = [(limpiar(numero), None) for numero in descripcion["numeros"]]
        viviendas = tuple(
            ViviendaPropuesta(numero, piso, nombre_de_vivienda(tipo, completo, numero)) for numero, piso in numeros
        )
        propuestas.append(AgrupacionPropuesta(etiqueta, nombre, viviendas))
    return propuestas
