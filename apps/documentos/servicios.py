"""Los documentos del conjunto activo: reglamento y manual de convivencia (HU-33). No sabe nada de HTTP.

Subir uno nuevo del mismo tipo archiva el anterior, no lo borra. Toda subida y toda descarga dejan
registro en la auditoría (la descarga: quién, qué documento y cuándo).
"""
import hashlib

from django.db import transaction

from apps.auditoria import servicios as auditoria
from apps.documentos.models import Documento, TipoDeDocumento

TAMANO_MAXIMO = 10 * 1024 * 1024  # bytes
FIRMA_DE_PDF = b"%PDF-"


class DocumentoInvalido(Exception):
    """El archivo no sirve como documento. Trae el mensaje para quien lo subió."""

    def __init__(self, mensaje):
        super().__init__(mensaje)
        self.mensaje = mensaje


def del_tipo(tipo):
    """Los documentos del conjunto activo de ese tipo, el más reciente primero y sin el contenido."""
    return Documento.objects.filter(tipo=tipo).select_related("subido_por").defer("contenido").order_by("-subido_en")


def vigente(tipo, con_contenido=False):
    """El documento más reciente de ese tipo en el conjunto activo, o None. Sin el contenido, salvo que se pida."""
    documentos = Documento.objects.filter(tipo=tipo).select_related("subido_por").order_by("-subido_en")
    return (documentos if con_contenido else documentos.defer("contenido")).first()


def vigentes():
    """Una entrada por tipo, en el orden del catálogo: `(tipo, documento vigente o None)`."""
    return [(tipo, vigente(tipo)) for tipo in TipoDeDocumento]


def versiones(tipo):
    """Todas las versiones de ese tipo, la más reciente (la vigente) primero. Sin el contenido."""
    return list(del_tipo(tipo))


def version(tipo, version_id, con_contenido=False):
    """Una versión de ese tipo en el conjunto activo, o None. Una de otro tipo o de otro conjunto no se encuentra."""
    documentos = Documento.objects.filter(tipo=tipo, pk=version_id).select_related("subido_por")
    return (documentos if con_contenido else documentos.defer("contenido")).first()


def guardar(actor, tipo, nombre, contenido):
    """Agrega la versión nueva del documento. La firma `%PDF-` del contenido decide si es un PDF; el nombre no."""
    etiqueta = TipoDeDocumento(tipo).label.lower()
    if not contenido:
        raise DocumentoInvalido("El archivo está vacío.")
    if len(contenido) > TAMANO_MAXIMO:
        raise DocumentoInvalido(f"El {etiqueta} no puede pesar más de {TAMANO_MAXIMO // (1024 * 1024)} MB.")
    if not contenido.startswith(FIRMA_DE_PDF):
        raise DocumentoInvalido("El archivo no es un PDF.")
    datos = {"nombre": nombre[:120], "peso": len(contenido), "huella": hashlib.sha256(contenido).hexdigest()}
    with transaction.atomic():
        documento = Documento.objects.create(tipo=tipo, contenido=contenido, subido_por=actor, **datos)
        auditoria.registrar(actor, "documento.subir", "Documento", documento.id, despues={"tipo": tipo, **datos})
    return documento


def registrar_descarga(actor, documento, archivada):
    """Deja en la auditoría quién descargó qué: la fecha la pone el registro. `archivada` es una versión que ya no es la vigente."""
    auditoria.registrar(
        actor,
        "documento.descargar",
        "Documento",
        documento.id,
        detalle={"tipo": documento.tipo, "version": "archivada" if archivada else "vigente"},
    )
