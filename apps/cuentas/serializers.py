from rest_framework import serializers


class IniciarSesionSerializer(serializers.Serializer):
    correo = serializers.EmailField()
    contrasena = serializers.CharField(trim_whitespace=False, write_only=True)


class ConjuntoResumenSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    nombre = serializers.CharField()


class ElegirConjuntoSerializer(serializers.Serializer):
    conjunto = serializers.UUIDField()
