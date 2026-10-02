from rest_framework import serializers

from apps.visitantes.models import Visitante


class RegistrarVisitanteSerializer(serializers.Serializer):
    nombre = serializers.CharField(max_length=120)
    cedula = serializers.CharField(max_length=20)
    ingresa_con_vehiculo = serializers.BooleanField(default=False)
    placa_vehiculo = serializers.CharField(max_length=10, required=False, allow_blank=True, default="")
    tipo_vehiculo = serializers.ChoiceField(
        choices=(("Auto", "Auto"), ("Moto", "Moto")),
        required=False,
        allow_blank=True,
        default="",
    )
    apartamento_visitado = serializers.UUIDField()

    def validate(self, datos):
        ingresa_con_vehiculo = datos["ingresa_con_vehiculo"]
        if ingresa_con_vehiculo:
            errores = {}
            if not datos["placa_vehiculo"]:
                errores["placa_vehiculo"] = ["Ingresa la placa del vehículo."]
            if not datos["tipo_vehiculo"]:
                errores["tipo_vehiculo"] = ["Selecciona Auto o Moto."]
            if errores:
                raise serializers.ValidationError(errores)
        else:
            datos["placa_vehiculo"] = ""
            datos["tipo_vehiculo"] = ""
        return datos


class VisitanteSerializer(serializers.ModelSerializer):
    apartamento_visitado = serializers.CharField(source="unidad.nombre", read_only=True)

    class Meta:
        model = Visitante
        fields = (
            "id",
            "nombre",
            "cedula",
            "placa_vehiculo",
            "tipo_vehiculo",
            "hora_entrada",
            "apartamento_visitado",
        )
