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


class EnviarSolicitudSerializer(serializers.Serializer):
    unidad = serializers.UUIDField()
    motivo = serializers.CharField(max_length=200)
    asistentes = serializers.IntegerField(min_value=1)
    observaciones = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")


class DecisionDeSolicitudSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=("RESERVADA", "RECHAZADA"))
    motivo = serializers.CharField(max_length=1000, trim_whitespace=True)


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
    # Qué reglas se evaluaron y con qué resultado (HU-13, plan P10).
    evaluacion = serializers.JSONField()
    evaluada_en = serializers.DateTimeField()
    motivo_decision = serializers.CharField()
    decidida_en = serializers.DateTimeField(allow_null=True)

    def get_area(self, solicitud):
        return {"id": solicitud.area_id, "nombre": solicitud.area.nombre}

    def get_segundos_restantes(self, solicitud):
        return servicios.segundos_restantes(solicitud)

    def get_unidad(self, solicitud):
        return {"id": solicitud.unidad_id, "nombre": solicitud.unidad.nombre} if solicitud.unidad else None


class SolicitudParaAdministrarSerializer(SolicitudSerializer):
    residente = serializers.SerializerMethodField()
    motivo_decision = serializers.CharField()
    decidida_por = serializers.SerializerMethodField()
    decidida_en = serializers.DateTimeField()

    def get_residente(self, solicitud):
        return {
            "id": solicitud.persona_id,
            "nombre": f"{solicitud.persona.nombres} {solicitud.persona.apellidos}",
        }

    def get_decidida_por(self, solicitud):
        if not solicitud.decidida_por:
            return None
        return {
            "id": solicitud.decidida_por_id,
            "nombre": f"{solicitud.decidida_por.nombres} {solicitud.decidida_por.apellidos}",
        }


class DetalleDeSolicitudSerializer(SolicitudSerializer):
    """Con las unidades a cuyo nombre puede solicitar y los avisos del panel, mientras está en trámite."""

    unidades_para_solicitar = serializers.SerializerMethodField()
    avisos = serializers.SerializerMethodField()

    def get_avisos(self, solicitud):
        return servicios.avisos(solicitud)

    def get_unidades_para_solicitar(self, solicitud):
        if solicitud.estado != "EN_SOLICITUD":
            return []
        return [{"id": unidad.id, "nombre": unidad.nombre} for unidad in unidades_para_solicitar(solicitud.persona)]
