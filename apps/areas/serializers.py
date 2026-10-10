from rest_framework import serializers

from apps.areas.models import ModoDeUso

MENSAJE_HORARIO = "La hora de cierre debe ser posterior a la de apertura."
MENSAJE_DURACION_MINIMA = "Cada reserva debe durar al menos 2 horas (120 minutos)."
MENSAJE_DURACION_SOLO_RESERVA = "La duración de la franja es solo para áreas con reserva."
MENSAJE_DURACION_OBLIGATORIA = "La duración de la franja es obligatoria en un área con reserva."
MENSAJE_PERMANENCIA_SOLO_INGRESO = "La permanencia máxima es solo para áreas con ingreso."
MENSAJE_PERMANENCIA_OBLIGATORIA = "La permanencia máxima es obligatoria en un área con ingreso."
MENSAJE_MODO_FIJO = "El modo de uso no cambia después de crear el área."


def validar_horario(apertura, cierre):
    if cierre <= apertura:
        raise serializers.ValidationError({"hora_cierre": [MENSAJE_HORARIO]})


class CrearAreaSerializer(serializers.Serializer):
    modo_uso = serializers.ChoiceField(choices=ModoDeUso.choices, required=False, default=ModoDeUso.RESERVA)
    nombre = serializers.CharField(max_length=80)
    descripcion = serializers.CharField(allow_blank=True, required=False, default="")
    hora_apertura = serializers.TimeField()
    hora_cierre = serializers.TimeField()
    duracion_franja_minutos = serializers.IntegerField(
        min_value=120,
        max_value=1440,
        required=False,
        allow_null=True,
        error_messages={"min_value": MENSAJE_DURACION_MINIMA},
    )
    permanencia_maxima_minutos = serializers.IntegerField(
        min_value=15, max_value=1440, required=False, allow_null=True
    )
    aforo_maximo = serializers.IntegerField(min_value=1, max_value=10000)

    def validate(self, datos):
        validar_horario(datos["hora_apertura"], datos["hora_cierre"])
        duracion = datos.get("duracion_franja_minutos")
        permanencia = datos.get("permanencia_maxima_minutos")
        errores = {}
        if datos["modo_uso"] == ModoDeUso.RESERVA:
            if duracion is None:
                errores["duracion_franja_minutos"] = [MENSAJE_DURACION_OBLIGATORIA]
            if permanencia is not None:
                errores["permanencia_maxima_minutos"] = [MENSAJE_PERMANENCIA_SOLO_INGRESO]
        else:
            if permanencia is None:
                errores["permanencia_maxima_minutos"] = [MENSAJE_PERMANENCIA_OBLIGATORIA]
            if duracion is not None:
                errores["duracion_franja_minutos"] = [MENSAJE_DURACION_SOLO_RESERVA]
        if errores:
            raise serializers.ValidationError(errores)
        datos["duracion_franja_minutos"] = duracion
        datos["permanencia_maxima_minutos"] = permanencia
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
    permanencia_maxima_minutos = serializers.IntegerField(min_value=15, max_value=1440, required=False)
    aforo_maximo = serializers.IntegerField(min_value=1, max_value=10000, required=False)
    en_mantenimiento = serializers.BooleanField(required=False)

    def to_internal_value(self, datos):
        # El modo se fija al crear (plan P3): no es un campo editable, y se dice por qué.
        if "modo_uso" in datos:
            raise serializers.ValidationError({"modo_uso": [MENSAJE_MODO_FIJO]})
        return super().to_internal_value(datos)

    def validate(self, datos):
        area = self.context["area"]
        validar_horario(datos.get("hora_apertura", area.hora_apertura), datos.get("hora_cierre", area.hora_cierre))
        if area.modo_uso == ModoDeUso.INGRESO and "duracion_franja_minutos" in datos:
            raise serializers.ValidationError({"duracion_franja_minutos": [MENSAJE_DURACION_SOLO_RESERVA]})
        if area.modo_uso == ModoDeUso.RESERVA and "permanencia_maxima_minutos" in datos:
            raise serializers.ValidationError({"permanencia_maxima_minutos": [MENSAJE_PERMANENCIA_SOLO_INGRESO]})
        return datos


class AreaSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    nombre = serializers.CharField()
    descripcion = serializers.CharField()
    hora_apertura = serializers.TimeField(format="%H:%M")
    hora_cierre = serializers.TimeField(format="%H:%M")
    modo_uso = serializers.CharField()
    duracion_franja_minutos = serializers.IntegerField(allow_null=True)
    permanencia_maxima_minutos = serializers.IntegerField(allow_null=True)
    aforo_maximo = serializers.IntegerField()
    en_mantenimiento = serializers.BooleanField()
    activo = serializers.BooleanField()
