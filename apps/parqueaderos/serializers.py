from rest_framework import serializers

from apps.parqueaderos.models import TipoDeParqueadero


class ConsultarParqueaderosSerializer(serializers.Serializer):
    tipo = serializers.ChoiceField(choices=TipoDeParqueadero.choices, required=False)
    libres = serializers.BooleanField(required=False, default=False)


class CrearParqueaderoSerializer(serializers.Serializer):
    """No hay campo de unidad: un parqueadero no se asigna aquí (HU-34 es otro plan)."""

    codigo = serializers.CharField(max_length=20, trim_whitespace=True)
    tipo = serializers.ChoiceField(choices=TipoDeParqueadero.choices)
    accesible = serializers.BooleanField(required=False, default=False)
    notas = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class ParqueaderoSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    codigo = serializers.CharField()
    tipo = serializers.CharField()
    accesible = serializers.BooleanField()
    notas = serializers.CharField()
    # Dice si está ocupado, no por quién: eso se ve en el listado de visitantes (plan P13).
    ocupado = serializers.SerializerMethodField()

    def get_ocupado(self, parqueadero):
        return getattr(parqueadero, "abiertas", 0) > 0
