from django.utils import timezone
from rest_framework import serializers

LARGO_MAXIMO = 2000


class RegistrarInfraccionSerializer(serializers.Serializer):
    """La vivienda se elige siempre a mano, también cuando nace de un caso: el caso no guarda vivienda."""

    unidad = serializers.UUIDField()
    descripcion_hecho = serializers.CharField(max_length=LARGO_MAXIMO, trim_whitespace=True)
    fecha_hecho = serializers.DateField()
    caso = serializers.UUIDField(required=False, allow_null=True, default=None)

    def validate_fecha_hecho(self, fecha):
        if fecha > timezone.localdate():
            raise serializers.ValidationError("La fecha del hecho no puede ser futura.")
        return fecha


class CerrarInfraccionSerializer(serializers.Serializer):
    """Solo el comentario: la fecha del cierre la pone el sistema y el hecho no se edita."""

    comentario = serializers.CharField(max_length=LARGO_MAXIMO, trim_whitespace=True)


class AnularInfraccionSerializer(serializers.Serializer):
    motivo = serializers.CharField(max_length=LARGO_MAXIMO, trim_whitespace=True)


def nombre_de(persona):
    return f"{persona.nombres} {persona.apellidos}" if persona else None


class RegistroSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    unidad = serializers.UUIDField(source="unidad_id")
    vivienda = serializers.CharField(source="unidad.nombre")
    caso = serializers.UUIDField(source="caso_id", allow_null=True)
    descripcion_hecho = serializers.CharField()
    fecha_hecho = serializers.DateField()
    registrado_por = serializers.SerializerMethodField()
    registrado_en = serializers.DateTimeField()
    fecha_notificacion = serializers.DateTimeField()
    abierto = serializers.BooleanField()
    cierre_fecha = serializers.DateTimeField(allow_null=True)
    cierre_comentario = serializers.CharField(allow_null=True)
    cerrado_por = serializers.SerializerMethodField()
    anulado = serializers.BooleanField()
    anulacion_motivo = serializers.CharField()
    anulado_por = serializers.SerializerMethodField()
    anulado_en = serializers.DateTimeField(allow_null=True)

    def get_registrado_por(self, registro):
        return nombre_de(registro.registrado_por)

    def get_cerrado_por(self, registro):
        return nombre_de(registro.cerrado_por)

    def get_anulado_por(self, registro):
        return nombre_de(registro.anulado_por)
