from rest_framework import serializers

from apps.parqueaderos.models import TipoDeParqueadero, TipoDeVehiculo


class ConsultarParqueaderosSerializer(serializers.Serializer):
    tipo = serializers.ChoiceField(choices=TipoDeParqueadero.choices, required=False)
    libres = serializers.BooleanField(required=False, default=False)


class CrearParqueaderoSerializer(serializers.Serializer):
    """No hay campo de unidad: un parqueadero se crea libre y se asigna después, solo si es de residentes."""

    codigo = serializers.CharField(max_length=20, trim_whitespace=True)
    tipo = serializers.ChoiceField(choices=TipoDeParqueadero.choices)
    vehiculo = serializers.ChoiceField(choices=TipoDeVehiculo.choices, required=False, default=TipoDeVehiculo.CARRO)
    accesible = serializers.BooleanField(required=False, default=False)
    notas = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class AsignarParqueaderoSerializer(serializers.Serializer):
    unidad = serializers.UUIDField()


def nombre_de(persona):
    return f"{persona.nombres} {persona.apellidos}" if persona else None


class ParqueaderoSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    codigo = serializers.CharField()
    tipo = serializers.CharField()
    vehiculo = serializers.CharField()
    accesible = serializers.BooleanField()
    notas = serializers.CharField()
    # Dice si está ocupado, no por quién: eso se ve en el listado de visitantes (plan P13).
    ocupado = serializers.SerializerMethodField()
    # Solo los de residentes: la vivienda a la que están asignados hoy, o null si están sin asignar.
    asignado_a = serializers.SerializerMethodField()

    def get_ocupado(self, parqueadero):
        return getattr(parqueadero, "abiertas", 0) > 0

    def get_asignado_a(self, parqueadero):
        vigente = getattr(parqueadero, "asignacion_vigente", [])
        return vigente[0].unidad.nombre if vigente else None


class AsignacionSerializer(serializers.Serializer):
    """Una fila del historial de un puesto."""

    id = serializers.UUIDField()
    unidad = serializers.UUIDField(source="unidad_id")
    vivienda = serializers.CharField(source="unidad.nombre")
    vigencia_desde = serializers.DateField()
    vigencia_hasta = serializers.DateField(allow_null=True)
    registrado_por = serializers.SerializerMethodField()
    cerrado_por = serializers.SerializerMethodField()

    def get_registrado_por(self, asignacion):
        return nombre_de(asignacion.registrado_por)

    def get_cerrado_por(self, asignacion):
        return nombre_de(asignacion.cerrado_por)


class ResultadoDeAsignacionSerializer(AsignacionSerializer):
    """La respuesta de asignar: la fila nueva y si fue una reasignación (cerró la anterior)."""

    parqueadero = serializers.UUIDField(source="parqueadero_id")
    reasignada = serializers.BooleanField()


class MiParqueaderoSerializer(serializers.Serializer):
    """Un puesto vigente de la vivienda de quien pregunta. Sin quién lo asignó."""

    id = serializers.UUIDField(source="parqueadero_id")
    codigo = serializers.CharField(source="parqueadero.codigo")
    vehiculo = serializers.CharField(source="parqueadero.vehiculo")
    accesible = serializers.BooleanField(source="parqueadero.accesible")
    notas = serializers.CharField(source="parqueadero.notas")
    vivienda = serializers.CharField(source="unidad.nombre")
    desde = serializers.DateField(source="vigencia_desde")
