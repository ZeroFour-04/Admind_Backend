from django.urls import path, register_converter

from apps.documentos.models import TipoDeDocumento
from apps.documentos.views import (
    ArchivoDeVersionView,
    ArchivoDelDocumentoView,
    DocumentosView,
    DocumentoView,
    VersionesView,
)


class TipoDeDocumentoConverter:
    """Solo deja pasar los tipos del catálogo: uno que no existe es 404 sin llegar a la vista."""

    regex = "|".join(TipoDeDocumento.values)

    def to_python(self, valor):
        return valor

    def to_url(self, valor):
        return valor


register_converter(TipoDeDocumentoConverter, "tipo_de_documento")

# Las rutas de `reglamento/…` que usa el asistente son el caso `tipo=reglamento` de estas.
urlpatterns = [
    path("", DocumentosView.as_view(), name="documentos"),
    path("<tipo_de_documento:tipo>/", DocumentoView.as_view(), name="documento"),
    path("<tipo_de_documento:tipo>/archivo/", ArchivoDelDocumentoView.as_view(), name="documento-archivo"),
    path("<tipo_de_documento:tipo>/versiones/", VersionesView.as_view(), name="documento-versiones"),
    path(
        "<tipo_de_documento:tipo>/versiones/<uuid:version_id>/archivo/",
        ArchivoDeVersionView.as_view(),
        name="documento-version-archivo",
    ),
]
