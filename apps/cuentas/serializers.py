from rest_framework import serializers


class IniciarSesionSerializer(serializers.Serializer):
    correo = serializers.EmailField()
    contrasena = serializers.CharField(trim_whitespace=False, write_only=True)
