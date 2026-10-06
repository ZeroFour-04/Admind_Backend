from rest_framework import serializers

from apps.unidades import estructura
from apps.unidades.estructura import Patron, clave
from apps.unidades.models import TipoDeVivienda, TipoVinculo

MAXIMO_DE_AGRUPACIONES = 60
MAXIMO_DE_VIVIENDAS = 2000


class UnidadSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    nombre = serializers.CharField()
    vinculos_vigentes = serializers.IntegerField(required=False)


class CrearUnidadSerializer(serializers.Serializer):
    nombre = serializers.CharField(max_length=40)


class AgrupacionPedidaSerializer(serializers.Serializer):
    nombre = serializers.CharField(max_length=40, allow_blank=True, default="")
    pisos = serializers.IntegerField(min_value=1, max_value=60, required=False)
    por_piso = serializers.IntegerField(min_value=1, max_value=40, required=False)
    cantidad = serializers.IntegerField(min_value=1, max_value=500, required=False)


class EspecificacionSerializer(serializers.Serializer):
    """Una tanda: qué viviendas, cómo se agrupan y cómo se numeran (HU-39)."""

    tipo_vivienda = serializers.ChoiceField(choices=TipoDeVivienda.choices)
    etiqueta = serializers.CharField(max_length=30, allow_blank=True, default="")
    patron = serializers.ChoiceField(choices=Patron.choices)
    primer_piso = serializers.IntegerField(min_value=1, max_value=20, default=1)
    desde = serializers.IntegerField(min_value=1, max_value=9999, default=1)
    numeros = serializers.ListField(child=serializers.CharField(max_length=12), max_length=500, required=False)
    agrupaciones = AgrupacionPedidaSerializer(many=True, allow_empty=False)

    def validate(self, datos):
        patron, pedidas = datos["patron"], datos["agrupaciones"]
        if len(pedidas) > MAXIMO_DE_AGRUPACIONES:
            raise serializers.ValidationError(f"Se registran hasta {MAXIMO_DE_AGRUPACIONES} agrupaciones a la vez.")
        nombres = [clave(pedida["nombre"]) for pedida in pedidas]
        if datos["etiqueta"].strip():
            if "" in nombres or len(set(nombres)) != len(nombres):
                raise serializers.ValidationError("Cada agrupación necesita un nombre distinto.")
        elif len(pedidas) != 1 or nombres[0]:
            raise serializers.ValidationError("Sin agrupaciones, las viviendas van en un solo grupo sin nombre.")
        if patron == Patron.PISO_CONSECUTIVO:
            if datos["tipo_vivienda"] != TipoDeVivienda.APARTAMENTO:
                raise serializers.ValidationError("La numeración por pisos es para apartamentos.")
            completo = all("pisos" in pedida and "por_piso" in pedida for pedida in pedidas)
        elif patron == Patron.LISTA:
            numeros = [clave(numero) for numero in datos.get("numeros", [])]
            completo = bool(numeros) and "" not in numeros and len(set(numeros)) == len(numeros)
        else:
            completo = all("cantidad" in pedida for pedida in pedidas)
        if not completo:
            raise serializers.ValidationError("Faltan datos para numerar las viviendas con ese patrón.")
        total = sum(len(propuesta.viviendas) for propuesta in estructura.generar(datos))
        if total > MAXIMO_DE_VIVIENDAS:
            raise serializers.ValidationError(
                f"Son {total} viviendas. Se registran hasta {MAXIMO_DE_VIVIENDAS} a la vez."
            )
        return datos


class AgrupacionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    nombre_completo = serializers.SerializerMethodField()
    tipo_vivienda = serializers.CharField()
    viviendas = serializers.IntegerField()

    def get_nombre_completo(self, agrupacion):
        return str(agrupacion)


class ResumenDeAgrupacionesSerializer(serializers.Serializer):
    agrupaciones = AgrupacionSerializer(many=True)
    sin_agrupar = serializers.IntegerField()
    total = serializers.IntegerField()


class VinculoSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    persona = serializers.SerializerMethodField()
    tipo = serializers.CharField()
    tipo_nombre = serializers.CharField(source="get_tipo_display")
    reside = serializers.BooleanField()
    vigencia_desde = serializers.DateField()
    vigencia_hasta = serializers.DateField()

    def get_persona(self, vinculo):
        return {"id": vinculo.persona_id, "nombre": str(vinculo.persona)}


class DetalleDeUnidadSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    nombre = serializers.CharField()
    vigentes = VinculoSerializer(many=True)
    historicos = VinculoSerializer(many=True)


class RegistrarVinculoSerializer(serializers.Serializer):
    persona = serializers.UUIDField()
    tipo = serializers.ChoiceField(choices=TipoVinculo.choices)
    reside = serializers.BooleanField()
    vigencia_desde = serializers.DateField(required=False)


class CerrarVinculoSerializer(serializers.Serializer):
    vigencia_hasta = serializers.DateField(required=False)
