"""El reglamento del conjunto activo (HU-33, lo mínimo). No sabe nada de HTTP."""
import hashlib

from django.db import transaction

from apps.auditoria import servicios as auditoria
from apps.documentos.models import Reglamento

TAMANO_MAXIMO = 10 * 1024 * 1024  # bytes
FIRMA_DE_PDF = b"%PDF-"


class ReglamentoInvalido(Exception):
    """El archivo no sirve como reglamento. Trae el mensaje para quien lo subió."""

    def __init__(self, mensaje):
        super().__init__(mensaje)
        self.mensaje = mensaje


def vigente(con_contenido=False):
    """El reglamento más reciente del conjunto activo, o None. Sin el contenido, salvo que se pida."""
    reglamentos = Reglamento.objects.select_related("subido_por").order_by("-subido_en")
    return (reglamentos if con_contenido else reglamentos.defer("contenido")).first()


def guardar(actor, nombre, contenido):
    """Agrega el reglamento nuevo. El anterior se conserva."""
    if not contenido:
        raise ReglamentoInvalido("El archivo está vacío.")
    if len(contenido) > TAMANO_MAXIMO:
        raise ReglamentoInvalido(f"El reglamento no puede pesar más de {TAMANO_MAXIMO // (1024 * 1024)} MB.")
    if not contenido.startswith(FIRMA_DE_PDF):
        raise ReglamentoInvalido("El archivo no es un PDF.")
    datos = {"nombre": nombre[:120], "peso": len(contenido), "huella": hashlib.sha256(contenido).hexdigest()}
    with transaction.atomic():
        reglamento = Reglamento.objects.create(contenido=contenido, subido_por=actor, **datos)
        auditoria.registrar(actor, "reglamento.subir", "Reglamento", reglamento.id, despues=datos)
    return reglamento
