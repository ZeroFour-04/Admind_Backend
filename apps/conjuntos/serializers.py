from rest_framework import serializers

from apps.conjuntos.models import Acento, Conjunto


class ConjuntoResumenSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    nombre = serializers.CharField()
    acento = serializers.CharField()


class ConjuntoListaSerializer(ConjuntoResumenSerializer):
    direccion = serializers.CharField()


class DatosDeConjuntoSerializer(serializers.Serializer):
    """Paso 1 del asistente. Al editar (PATCH) todos los campos son opcionales."""

    nombre = serializers.CharField(max_length=80)
    direccion = serializers.CharField(max_length=200, allow_blank=True, required=False)
    acento = serializers.ChoiceField(choices=Acento.choices, required=False)

    def validate_nombre(self, valor):
        valor = valor.strip()
        if not valor:
            raise serializers.ValidationError("El nombre del conjunto es obligatorio.")
        repetidos = Conjunto.objects.filter(nombre__iexact=valor, activo=True)
        if self.instance is not None:
            repetidos = repetidos.exclude(pk=self.instance.pk)
        if repetidos.exists():
            raise serializers.ValidationError("Ya existe un conjunto con ese nombre.")
        return valor

    def validate_direccion(self, valor):
        return valor.strip()
