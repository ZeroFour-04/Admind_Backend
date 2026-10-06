from rest_framework import serializers

from apps.reglas import servicios
from apps.reglas.catalogo import NIVEL_POR_TIPO, TipoDeRegla, describir


class CrearReglaSerializer(serializers.Serializer):
    # El área solo va en las reglas de un área; si sobra o falta, lo dice el servicio (HU-10).
    area = serializers.UUIDField(required=False, allow_null=True, default=None)
    tipo = serializers.ChoiceField(choices=[(tipo.value, tipo.label) for tipo in NIVEL_POR_TIPO])
    parametros = serializers.JSONField()
    vigencia_desde = serializers.DateField()


class EditarReglaSerializer(serializers.Serializer):
    """Solo los parámetros: el tipo y el área no cambian. Guardar crea una versión nueva."""

    parametros = serializers.JSONField()


class ReglaSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    area = serializers.SerializerMethodField()
    nivel = serializers.SerializerMethodField()
    tipo = serializers.CharField()
    tipo_nombre = serializers.CharField(source="get_tipo_display")
    parametros = serializers.JSONField()
    descripcion = serializers.SerializerMethodField()
    # Solo en «días que no abre»: las reservas ya apartadas que quedaron dentro de un cierre (plan D2 a).
    reservas_afectadas = serializers.SerializerMethodField()
    vigencia_desde = serializers.DateField()
    vigencia_hasta = serializers.DateField()
    reemplaza = serializers.UUIDField(source="reemplaza_id")
    creada_por = serializers.SerializerMethodField()
    creada_en = serializers.DateTimeField()

    def get_area(self, regla):
        return {"id": regla.area_id, "nombre": regla.area.nombre} if regla.area_id else None

    def get_nivel(self, regla):
        nivel = NIVEL_POR_TIPO.get(regla.tipo)
        return nivel.value if nivel else None

    def get_descripcion(self, regla):
        return describir(regla.tipo, regla.parametros)

    def get_reservas_afectadas(self, regla):
        if regla.tipo != TipoDeRegla.DIAS_QUE_NO_ABRE or regla.vigencia_hasta is not None:
            return 0
        return servicios.reservas_en_cierre(regla.area, regla.parametros["renglones"])

    def get_creada_por(self, regla):
        return str(regla.creada_por)
