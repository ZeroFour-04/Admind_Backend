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
    # El puesto de visitantes que ocupa mientras no tenga salida. Si existe y está libre lo decide el servicio.
    parqueadero = serializers.UUIDField(required=False, allow_null=True, default=None)

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
            if datos["parqueadero"] is not None:
                raise serializers.ValidationError(
                    {"parqueadero": ["Solo una visita con vehículo puede ocupar un parqueadero."]}
                )
        return datos


class VisitanteSerializer(serializers.ModelSerializer):
    apartamento_visitado = serializers.CharField(source="unidad.nombre", read_only=True)
    # El código del puesto, o `None` si no ocupó ninguno.
    parqueadero = serializers.SerializerMethodField()

    def get_parqueadero(self, visitante):
        return visitante.parqueadero.codigo if visitante.parqueadero_id else None

    class Meta:
        model = Visitante
        fields = (
            "id",
            "nombre",
            "cedula",
            "placa_vehiculo",
            "tipo_vehiculo",
            "hora_entrada",
            "hora_salida",
            "apartamento_visitado",
            "parqueadero",
        )
