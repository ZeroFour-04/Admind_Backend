from rest_framework import serializers

from apps.citas.models import Cita


class DiaHorarioSerializer(serializers.Serializer):
    dia = serializers.IntegerField(min_value=0, max_value=6)
    activo = serializers.BooleanField()
    hora_inicio = serializers.TimeField(allow_null=True)
    hora_fin = serializers.TimeField(allow_null=True)
    descanso_inicio = serializers.TimeField(allow_null=True)
    descanso_fin = serializers.TimeField(allow_null=True)

    def validate(self, datos):
        inicio = datos["hora_inicio"]
        fin = datos["hora_fin"]
        descanso_inicio = datos["descanso_inicio"]
        descanso_fin = datos["descanso_fin"]

        if not datos["activo"]:
            if any((inicio, fin, descanso_inicio, descanso_fin)):
                raise serializers.ValidationError("Un día no laborable no puede tener horario.")
            return datos

        if inicio is None or fin is None:
            raise serializers.ValidationError("Indica la hora de inicio y de cierre.")
        if inicio >= fin:
            raise serializers.ValidationError("La hora de cierre debe ser posterior a la de inicio.")
        if (descanso_inicio is None) != (descanso_fin is None):
            raise serializers.ValidationError("Indica las dos horas del almuerzo o deja ambas vacías.")
        if descanso_inicio is not None and (
            descanso_inicio < inicio or descanso_fin > fin or descanso_inicio >= descanso_fin
        ):
            raise serializers.ValidationError("El descanso debe estar dentro del horario de atención.")
        return datos


class HorarioDeAtencionSerializer(serializers.Serializer):
    dias = DiaHorarioSerializer(many=True)

    def validate_dias(self, dias):
        dias_recibidos = [dia["dia"] for dia in dias]
        if sorted(dias_recibidos) != list(range(7)):
            raise serializers.ValidationError("Configura una sola vez cada día de la semana.")
        return sorted(dias, key=lambda dia: dia["dia"])


class DisponibilidadSerializer(serializers.Serializer):
    fecha = serializers.DateField(required=False)


class AgendarCitaSerializer(serializers.Serializer):
    fecha = serializers.DateField()
    hora_inicio = serializers.TimeField()


class FranjaCitaSerializer(serializers.Serializer):
    hora_inicio = serializers.TimeField()
    hora_fin = serializers.TimeField()
    estado = serializers.ChoiceField(choices=["libre", "ocupada", "pasada", "propia"])


class CitaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cita
        fields = ["id", "fecha", "hora_inicio", "hora_fin"]


class CitaAdministracionSerializer(CitaSerializer):
    residente = serializers.SerializerMethodField()

    class Meta(CitaSerializer.Meta):
        fields = ["id", "fecha", "hora_inicio", "hora_fin", "estado", "residente"]

    def get_residente(self, cita):
        return f"{cita.persona.nombres} {cita.persona.apellidos}"
