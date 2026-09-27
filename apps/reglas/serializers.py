from rest_framework import serializers

from apps.reglas.catalogo import TipoDeRegla, describir


class CrearReglaSerializer(serializers.Serializer):
    # Tipo, parámetros, área y vigencia: sin cualquiera de ellos, 400 (HU-10).
    area = serializers.UUIDField()
    tipo = serializers.ChoiceField(choices=TipoDeRegla.choices)
    parametros = serializers.JSONField()
    vigencia_desde = serializers.DateField()


class EditarReglaSerializer(serializers.Serializer):
    """Solo los parámetros: el tipo y el área no cambian. Guardar crea una versión nueva."""

    parametros = serializers.JSONField()


class ReglaSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    area = serializers.SerializerMethodField()
    tipo = serializers.CharField()
    tipo_nombre = serializers.CharField(source="get_tipo_display")
    parametros = serializers.JSONField()
    descripcion = serializers.SerializerMethodField()
    vigencia_desde = serializers.DateField()
    vigencia_hasta = serializers.DateField()
    reemplaza = serializers.UUIDField(source="reemplaza_id")
    creada_por = serializers.SerializerMethodField()
    creada_en = serializers.DateTimeField()

    def get_area(self, regla):
        return {"id": regla.area_id, "nombre": regla.area.nombre}

    def get_descripcion(self, regla):
        return describir(regla.tipo, regla.parametros)

    def get_creada_por(self, regla):
        return str(regla.creada_por)
