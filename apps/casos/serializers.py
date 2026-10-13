from rest_framework import serializers

from apps.casos.models import Caso, CausalDeDescarte, FotoDeCaso, PrioridadCaso


class CrearCasoSerializer(serializers.Serializer):
    titulo = serializers.CharField(max_length=120)
    caso = serializers.CharField(max_length=4000, trim_whitespace=True)
    foto = serializers.FileField(required=False, allow_empty_file=True)


class RechazarCasoSerializer(serializers.Serializer):
    """El rechazo de fondo de Administración: el motivo cuenta como la respuesta obligatoria."""

    motivo = serializers.CharField(max_length=4000, allow_blank=False, trim_whitespace=True)


class DescartarCasoSerializer(serializers.Serializer):
    """El descarte de Secretaría: causal de lista cerrada, sin «otro», y comentario para el residente."""

    causal = serializers.ChoiceField(choices=CausalDeDescarte.choices)
    motivo = serializers.CharField(max_length=4000, allow_blank=False, trim_whitespace=True)


class RedirigirCasoSerializer(serializers.Serializer):
    nota = serializers.CharField(max_length=2000, required=False, allow_blank=True, trim_whitespace=True, default="")


class ResponderCasoSerializer(serializers.Serializer):
    respuesta = serializers.CharField(max_length=4000, allow_blank=False, trim_whitespace=True)


class PriorizarCasoSerializer(serializers.Serializer):
    prioridad = serializers.ChoiceField(choices=PrioridadCaso.choices)
    justificacion = serializers.CharField(
        max_length=1000, required=False, allow_blank=True, trim_whitespace=True, default=""
    )

    def validate(self, datos):
        if datos["prioridad"] == PrioridadCaso.URGENTE and not datos["justificacion"]:
            raise serializers.ValidationError({"justificacion": ["La prioridad urgente lleva una justificación escrita."]})
        return datos


class ConsultarCasosSerializer(serializers.Serializer):
    ver = serializers.ChoiceField(choices=("todos", "abiertos"), required=False, default="todos")
    orden = serializers.ChoiceField(choices=("prioridad", "antiguedad"), required=False, default="prioridad")


class CasoSerializer(serializers.ModelSerializer):
    """Lo que ve quien abrió el caso. Sin la nota interna, sin la justificación y sin quién actuó."""

    foto_id = serializers.SerializerMethodField()
    autor = serializers.SerializerMethodField()
    apartamento = serializers.SerializerMethodField()
    estado_nombre = serializers.CharField(source="get_estado_display", read_only=True)
    prioridad_nombre = serializers.CharField(source="get_prioridad_display", read_only=True)
    causal_rechazo_nombre = serializers.CharField(source="get_causal_rechazo_display", read_only=True)

    class Meta:
        model = Caso
        fields = (
            "id", "titulo", "cuerpo", "estado", "estado_nombre", "prioridad", "prioridad_nombre",
            "respuesta", "motivo_rechazo", "causal_rechazo", "causal_rechazo_nombre", "autor", "apartamento",
            "creado_en", "cerrado_en", "foto_id",
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


class CasoParaGestionSerializer(CasoSerializer):
    """Lo mismo, más lo que solo le sirve a gestión."""

    cerrado_por = serializers.SerializerMethodField()

    class Meta(CasoSerializer.Meta):
        fields = (*CasoSerializer.Meta.fields, "justificacion_prioridad", "nota_redireccion", "cerrado_por")

    def get_cerrado_por(self, caso):
        if caso.cerrado_por is None:
            return None
        return f"{caso.cerrado_por.nombres} {caso.cerrado_por.apellidos}"
