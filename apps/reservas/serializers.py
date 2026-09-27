from rest_framework import serializers

from apps.reservas import servicios
from apps.unidades.servicios import unidades_para_solicitar


class ConsultarFranjasSerializer(serializers.Serializer):
    area = serializers.UUIDField()
    fecha = serializers.DateField()


class FranjaSerializer(serializers.Serializer):
    hora_inicio = serializers.TimeField(format="%H:%M")
    hora_fin = serializers.TimeField(format="%H:%M")
    estado = serializers.CharField()


class TomarBloqueoSerializer(serializers.Serializer):
    area = serializers.UUIDField()
    fecha = serializers.DateField()
    hora_inicio = serializers.TimeField()


class SolicitudSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    area = serializers.SerializerMethodField()
    fecha = serializers.DateField()
    hora_inicio = serializers.TimeField(format="%H:%M")
    hora_fin = serializers.TimeField(format="%H:%M")
    estado = serializers.CharField()
    estado_nombre = serializers.CharField(source="get_estado_display")
    bloqueo_vence_en = serializers.DateTimeField()
    segundos_restantes = serializers.SerializerMethodField()
    motivo_liberacion = serializers.CharField()
    unidad = serializers.SerializerMethodField()
    motivo = serializers.CharField()
    asistentes = serializers.IntegerField()
    observaciones = serializers.CharField()
    creada_en = serializers.DateTimeField()
    enviada_en = serializers.DateTimeField()

    def get_area(self, solicitud):
        return {"id": solicitud.area_id, "nombre": solicitud.area.nombre}

    def get_segundos_restantes(self, solicitud):
        return servicios.segundos_restantes(solicitud)

    def get_unidad(self, solicitud):
        return {"id": solicitud.unidad_id, "nombre": solicitud.unidad.nombre} if solicitud.unidad else None


class DetalleDeSolicitudSerializer(SolicitudSerializer):
    """Con las unidades a cuyo nombre puede solicitar, mientras está en trámite."""

    unidades_para_solicitar = serializers.SerializerMethodField()

    def get_unidades_para_solicitar(self, solicitud):
        if solicitud.estado != "EN_SOLICITUD":
            return []
        return [{"id": unidad.id, "nombre": unidad.nombre} for unidad in unidades_para_solicitar(solicitud.persona)]
