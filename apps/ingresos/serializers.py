from rest_framework import serializers

from apps.areas.serializers import AreaSerializer


class BuscarResidenteSerializer(serializers.Serializer):
    # Llega por POST para que el documento no viaje en la URL (plan P11). Puede traer puntos y espacios.
    numero_documento = serializers.CharField(max_length=30)


class RegistrarIngresoSerializer(serializers.Serializer):
    area = serializers.UUIDField()
    persona = serializers.UUIDField()
    unidad = serializers.UUIDField()
    acompanantes = serializers.IntegerField(min_value=0, max_value=50, required=False, default=0)


class ConsultarIngresosSerializer(serializers.Serializer):
    area = serializers.UUIDField(required=False)
    fecha = serializers.DateField(required=False)


class UnidadDelResidenteSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    nombre = serializers.CharField()


class ResidenteSerializer(serializers.Serializer):
    """Nombre y viviendas, nada más: sin teléfono, correo ni documento (plan P11)."""

    persona = serializers.UUIDField(source="persona.id")
    nombre = serializers.SerializerMethodField()
    unidades = UnidadDelResidenteSerializer(many=True)

    def get_nombre(self, residente):
        return str(residente["persona"])


class ZonaSerializer(serializers.Serializer):
    """Los cupos son un conteo, sin nombres (plan P17)."""

    area = AreaSerializer()
    adentro = serializers.IntegerField()
    cupos = serializers.IntegerField()
    abierta_ahora = serializers.BooleanField()
    motivo_cierre = serializers.CharField()


class IngresoSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    area = serializers.SerializerMethodField()
    persona = serializers.SerializerMethodField()
    unidad = UnidadDelResidenteSerializer()
    acompanantes = serializers.IntegerField()
    estado = serializers.CharField()
    estado_nombre = serializers.CharField(source="get_estado_display")
    entrada_en = serializers.DateTimeField()
    salida_prevista_en = serializers.DateTimeField()
    salida_en = serializers.DateTimeField()
    registrado_por = serializers.SerializerMethodField()
    salida_registrada_por = serializers.SerializerMethodField()

    def get_area(self, ingreso):
        return {"id": ingreso.area_id, "nombre": ingreso.area.nombre}

    def get_persona(self, ingreso):
        return {"id": ingreso.persona_id, "nombre": str(ingreso.persona)}

    def get_registrado_por(self, ingreso):
        return str(ingreso.registrado_por)

    def get_salida_registrada_por(self, ingreso):
        return str(ingreso.salida_registrada_por) if ingreso.salida_registrada_por_id else None
