from rest_framework import serializers

from apps.unidades.models import TipoVinculo


class UnidadSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    nombre = serializers.CharField()
    vinculos_vigentes = serializers.IntegerField(required=False)


class CrearUnidadSerializer(serializers.Serializer):
    nombre = serializers.CharField(max_length=40)


class VinculoSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    persona = serializers.SerializerMethodField()
    tipo = serializers.CharField()
    tipo_nombre = serializers.CharField(source="get_tipo_display")
    reside = serializers.BooleanField()
    vigencia_desde = serializers.DateField()
    vigencia_hasta = serializers.DateField()

    def get_persona(self, vinculo):
        return {"id": vinculo.persona_id, "nombre": str(vinculo.persona)}


class DetalleDeUnidadSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    nombre = serializers.CharField()
    vigentes = VinculoSerializer(many=True)
    historicos = VinculoSerializer(many=True)


class RegistrarVinculoSerializer(serializers.Serializer):
    persona = serializers.UUIDField()
    tipo = serializers.ChoiceField(choices=TipoVinculo.choices)
    reside = serializers.BooleanField()
    vigencia_desde = serializers.DateField(required=False)


class CerrarVinculoSerializer(serializers.Serializer):
    vigencia_hasta = serializers.DateField(required=False)
