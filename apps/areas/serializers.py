from rest_framework import serializers

MENSAJE_HORARIO = "La hora de cierre debe ser posterior a la de apertura."
MENSAJE_DURACION_MINIMA = "Cada reserva debe durar al menos 2 horas (120 minutos)."


def validar_horario(apertura, cierre):
    if cierre <= apertura:
        raise serializers.ValidationError({"hora_cierre": [MENSAJE_HORARIO]})


class CrearAreaSerializer(serializers.Serializer):
    nombre = serializers.CharField(max_length=80)
    descripcion = serializers.CharField(allow_blank=True, required=False, default="")
    hora_apertura = serializers.TimeField()
    hora_cierre = serializers.TimeField()
    duracion_franja_minutos = serializers.IntegerField(
        min_value=120, max_value=1440, error_messages={"min_value": MENSAJE_DURACION_MINIMA}
    )
    aforo_maximo = serializers.IntegerField(min_value=1, max_value=10000)

    def validate(self, datos):
        validar_horario(datos["hora_apertura"], datos["hora_cierre"])
        return datos


class EditarAreaSerializer(serializers.Serializer):
    """Nombre, descripción, horario, aforo y mantenimiento."""

    nombre = serializers.CharField(max_length=80, required=False)
    descripcion = serializers.CharField(allow_blank=True, required=False)
    hora_apertura = serializers.TimeField(required=False)
    hora_cierre = serializers.TimeField(required=False)
    duracion_franja_minutos = serializers.IntegerField(
        min_value=120,
        max_value=1440,
        required=False,
        error_messages={"min_value": MENSAJE_DURACION_MINIMA},
    )
    aforo_maximo = serializers.IntegerField(min_value=1, max_value=10000, required=False)
    en_mantenimiento = serializers.BooleanField(required=False)

    def validate(self, datos):
        area = self.context["area"]
        validar_horario(datos.get("hora_apertura", area.hora_apertura), datos.get("hora_cierre", area.hora_cierre))
        return datos


class AreaSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    nombre = serializers.CharField()
    descripcion = serializers.CharField()
    hora_apertura = serializers.TimeField(format="%H:%M")
    hora_cierre = serializers.TimeField(format="%H:%M")
    duracion_franja_minutos = serializers.IntegerField()
    aforo_maximo = serializers.IntegerField()
    en_mantenimiento = serializers.BooleanField()
    activo = serializers.BooleanField()
