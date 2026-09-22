from rest_framework import serializers


class UnidadSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    nombre = serializers.CharField()
