from rest_framework import serializers

from apps.documentos.models import TipoDeDocumento


class SubirDocumentoSerializer(serializers.Serializer):
    archivo = serializers.FileField()


class DocumentoSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    nombre = serializers.CharField()
    peso = serializers.IntegerField()
    subido_en = serializers.DateTimeField()
    subido_por = serializers.SerializerMethodField()

    def get_subido_por(self, documento):
        return str(documento.subido_por)


class VersionSerializer(DocumentoSerializer):
    """Una fila de la lista de versiones: lo mismo y si es la vigente. La vista le pone `vigente`."""

    vigente = serializers.BooleanField()


def datos_del_documento(tipo, documento):
    """Lo que ve quien consulta un tipo: `cargado: false`, o los datos del vigente sin el contenido."""
    base = {"tipo": tipo, "tipo_nombre": TipoDeDocumento(tipo).label}
    if documento is None:
        return {**base, "cargado": False}
    return {**base, "cargado": True, **DocumentoSerializer(documento).data}
