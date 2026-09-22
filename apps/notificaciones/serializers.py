from rest_framework import serializers


class NotificacionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    titulo = serializers.CharField()
    cuerpo = serializers.CharField()
    origen = serializers.CharField()
    referencia = serializers.UUIDField()
    creada_en = serializers.DateTimeField()
