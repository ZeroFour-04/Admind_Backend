from rest_framework import serializers

from apps.areas.models import Clasificacion

MENSAJE_HORARIO = "La hora de cierre debe ser posterior a la de apertura."


def validar_horario(apertura, cierre):
    if cierre <= apertura:
        raise serializers.ValidationError({"hora_cierre": [MENSAJE_HORARIO]})


class CrearAreaSerializer(serializers.Serializer):
    nombre = serializers.CharField(max_length=80)
    descripcion = serializers.CharField(allow_blank=True, required=False, default="")
    # Obligatoria y sin valor por defecto: hay que elegirla de la lista cerrada (HU-09).
    clasificacion = serializers.ChoiceField(choices=Clasificacion.choices)
    hora_apertura = serializers.TimeField()
    hora_cierre = serializers.TimeField()
    duracion_franja_minutos = serializers.IntegerField(min_value=1, max_value=1440)

    def validate(self, datos):
        validar_horario(datos["hora_apertura"], datos["hora_cierre"])
        return datos


class EditarAreaSerializer(serializers.Serializer):
    """Nombre, descripción, horario y mantenimiento. La clasificación no se cambia aquí."""

    nombre = serializers.CharField(max_length=80, required=False)
    descripcion = serializers.CharField(allow_blank=True, required=False)
    hora_apertura = serializers.TimeField(required=False)
    hora_cierre = serializers.TimeField(required=False)
    duracion_franja_minutos = serializers.IntegerField(min_value=1, max_value=1440, required=False)
    en_mantenimiento = serializers.BooleanField(required=False)

    def validate(self, datos):
        area = self.context["area"]
        validar_horario(datos.get("hora_apertura", area.hora_apertura), datos.get("hora_cierre", area.hora_cierre))
        return datos


class AreaSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    nombre = serializers.CharField()
    descripcion = serializers.CharField()
    clasificacion = serializers.CharField()
    clasificacion_nombre = serializers.CharField(source="get_clasificacion_display")
    es_esencial = serializers.BooleanField()
    hora_apertura = serializers.TimeField(format="%H:%M")
    hora_cierre = serializers.TimeField(format="%H:%M")
    duracion_franja_minutos = serializers.IntegerField()
    en_mantenimiento = serializers.BooleanField()
    activo = serializers.BooleanField()
