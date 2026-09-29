"""Ancho y alto de una imagen, leídos de su cabecera (HU-21).

Basta para exigir que la foto del conjunto sea cuadrada sin agregar una librería de imágenes:
no se decodifica ningún píxel, solo se leen los bytes donde cada formato guarda su tamaño.
"""
import struct


def dimensiones(contenido, tipo):
    """(ancho, alto) en píxeles, o None si la cabecera no se puede leer."""
    lector = LECTORES.get(tipo)
    if lector is None:
        return None
    try:
        return lector(contenido)
    except (struct.error, IndexError):
        return None


def _png(contenido):
    # Tras la firma de 8 bytes va el bloque IHDR: longitud, nombre, y ancho y alto en 4 bytes cada uno.
    if contenido[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", contenido[16:24])


# Marcadores de inicio de cuadro (SOF) que traen el tamaño. C4, C8 y CC usan el mismo rango para otra cosa.
MARCADORES_SOF = set(range(0xC0, 0xD0)) - {0xC4, 0xC8, 0xCC}


def _jpeg(contenido):
    # Se saltan los segmentos (cada uno dice cuánto mide) hasta el de inicio de cuadro.
    posicion = 2
    while posicion < len(contenido):
        if contenido[posicion] != 0xFF:
            return None
        marcador = contenido[posicion + 1]
        if marcador == 0xFF:  # relleno entre segmentos
            posicion += 1
            continue
        if marcador == 0x01 or 0xD0 <= marcador <= 0xD8:  # marcadores sin longitud
            posicion += 2
            continue
        (longitud,) = struct.unpack(">H", contenido[posicion + 2 : posicion + 4])
        if marcador in MARCADORES_SOF:
            # Longitud (2), precisión (1), y después alto y ancho en 2 bytes cada uno.
            alto, ancho = struct.unpack(">HH", contenido[posicion + 5 : posicion + 9])
            return ancho, alto
        posicion += 2 + longitud
    return None


def _webp(contenido):
    fragmento = contenido[12:16]
    if fragmento == b"VP8 ":
        # Con pérdida: tras la marca 9D 01 2A van ancho y alto en 14 bits, little-endian.
        if contenido[23:26] != b"\x9d\x01\x2a":
            return None
        ancho, alto = struct.unpack("<HH", contenido[26:30])
        return ancho & 0x3FFF, alto & 0x3FFF
    if fragmento == b"VP8L":
        # Sin pérdida: tras la firma 0x2F, ancho menos uno y alto menos uno en 14 bits cada uno.
        if contenido[20] != 0x2F:
            return None
        bits = int.from_bytes(contenido[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if fragmento == b"VP8X":
        # Extendido: ancho menos uno y alto menos uno en 24 bits cada uno.
        if len(contenido) < 30:
            return None
        return int.from_bytes(contenido[24:27], "little") + 1, int.from_bytes(contenido[27:30], "little") + 1
    return None


LECTORES = {"image/png": _png, "image/jpeg": _jpeg, "image/webp": _webp}
