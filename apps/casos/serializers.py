from rest_framework import serializers

from apps.casos.models import Caso, FotoDeCaso


class CrearCasoSerializer(serializers.Serializer):
    titulo = serializers.CharField(max_length=120)
    caso = serializers.CharField(max_length=4000, trim_whitespace=True)
    foto = serializers.FileField(required=False, allow_empty_file=True)


class RechazarCasoSerializer(serializers.Serializer):
    motivo = serializers.CharField(max_length=4000, allow_blank=False, trim_whitespace=True)


class CasoSerializer(serializers.ModelSerializer):
    foto_id = serializers.SerializerMethodField()
    autor = serializers.SerializerMethodField()
    apartamento = serializers.SerializerMethodField()

    class Meta:
        model = Caso
        fields = (
            "id", "titulo", "cuerpo", "estado", "prioridad", "motivo_rechazo", "autor", "apartamento",
            "creado_en", "foto_id"
        )

    def get_foto_id(self, caso):
        foto = getattr(caso, "foto_cargada", None)
        if isinstance(foto, (list, tuple)):
            foto = foto[0] if foto else None
        if foto is None:
            try:
                foto = caso.foto
            except FotoDeCaso.DoesNotExist:
                return None
        return str(foto.id) if foto else None

    def get_autor(self, caso):
        return f"{caso.autor.nombres} {caso.autor.apellidos}"

    def get_apartamento(self, caso):
        vinculos = getattr(caso.autor, "vinculos_residenciales_actuales", ())
        return ", ".join(vinculo.unidad.nombre for vinculo in vinculos)
