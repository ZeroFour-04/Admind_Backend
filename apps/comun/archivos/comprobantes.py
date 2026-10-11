"""Validación compartida de un comprobante de pago (HU-16). No sabe nada de HTTP ni de apps de negocio.

El tipo del archivo lo decide su firma —los primeros bytes—, no la extensión ni el `Content-Type`
que escribe quien lo sube. Por eso las firmas de imagen se escriben aquí en vez de traer
`tipo_real_de_imagen` de `conjuntos`: `comun` no importa apps de negocio.
"""
import hashlib

TAMANO_MAXIMO_DE_COMPROBANTE = 5 * 1024 * 1024  # bytes

FIRMAS = {
    "application/pdf": lambda inicio: inicio.startswith(b"%PDF-"),
    "image/png": lambda inicio: inicio.startswith(b"\x89PNG\r\n\x1a\n"),
    "image/jpeg": lambda inicio: inicio.startswith(b"\xff\xd8\xff"),
}


class ArchivoInvalido(Exception):
    """El archivo no sirve como comprobante. Trae el mensaje para quien lo subió."""

    def __init__(self, mensaje):
        super().__init__(mensaje)
        self.mensaje = mensaje


def tipo_real(contenido):
    """El tipo según la firma del archivo, o None si no es PDF, PNG ni JPG."""
    inicio = bytes(contenido[:16])
    return next((tipo for tipo, es_de_este_tipo in FIRMAS.items() if es_de_este_tipo(inicio)), None)


def validar_comprobante(contenido):
    """Devuelve `{"tipo", "peso", "huella"}` o lanza `ArchivoInvalido`: vacío, muy pesado o de un tipo que no sirve."""
    if not contenido:
        raise ArchivoInvalido("El archivo está vacío.")
    if len(contenido) > TAMANO_MAXIMO_DE_COMPROBANTE:
        raise ArchivoInvalido(
            f"El comprobante no puede pesar más de {TAMANO_MAXIMO_DE_COMPROBANTE // (1024 * 1024)} MB."
        )
    tipo = tipo_real(contenido)
    if tipo is None:
        raise ArchivoInvalido("El comprobante debe ser un PDF o una imagen JPG o PNG.")
    return {"tipo": tipo, "peso": len(contenido), "huella": hashlib.sha256(contenido).hexdigest()}
