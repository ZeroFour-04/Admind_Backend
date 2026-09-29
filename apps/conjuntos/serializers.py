from rest_framework import serializers

from apps.conjuntos.models import Acento, Conjunto


class ConjuntoResumenSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    nombre = serializers.CharField()
    acento = serializers.CharField()
    # El hex elegido con el acento personalizado, o null con uno del catálogo.
    color = serializers.SerializerMethodField()
    # Huella de la foto, o null sin foto: entonces la interfaz muestra un marcador (HU-21).
    logo = serializers.SerializerMethodField()

    def get_color(self, conjunto):
        return conjunto.color_personalizado or None

    def get_logo(self, conjunto):
        return conjunto.logo_huella or None


class ConjuntoListaSerializer(ConjuntoResumenSerializer):
    direccion = serializers.CharField()


def color_hex():
    return serializers.RegexField(
        r"^#[0-9a-fA-F]{6}$",
        required=False,
        error_messages={"invalid": "El color debe ser un hex como #1a2b3c."},
    )


def validar_color(datos):
    """El personalizado va con su color; los del catálogo, sin color.

    Deja el color en `color_personalizado`, como lo guarda el modelo. Al pasar a un acento del
    catálogo lo vacía, para que no quede un color viejo guardado.
    """
    color = datos.pop("color", None)
    acento = datos.get("acento")
    if acento is None:
        if color is not None:
            raise serializers.ValidationError({"acento": ["Para usar un color propio, elige el acento personalizado."]})
    elif acento == Acento.PERSONALIZADO:
        if color is None:
            raise serializers.ValidationError({"color": ["Elige el color del conjunto."]})
        datos["color_personalizado"] = color.lower()
    else:
        if color is not None:
            raise serializers.ValidationError({"color": ["El color propio solo va con el acento personalizado."]})
        datos["color_personalizado"] = ""
    return datos


class DatosDeConjuntoSerializer(serializers.Serializer):
    """Paso 1 del asistente. Al editar (PATCH) todos los campos son opcionales."""

    nombre = serializers.CharField(max_length=80)
    direccion = serializers.CharField(max_length=200, allow_blank=True, required=False)
    acento = serializers.ChoiceField(choices=Acento.choices, required=False)
    color = color_hex()

    def validate_nombre(self, valor):
        valor = valor.strip()
        if not valor:
            raise serializers.ValidationError("El nombre del conjunto es obligatorio.")
        repetidos = Conjunto.objects.filter(nombre__iexact=valor, activo=True)
        if self.instance is not None:
            repetidos = repetidos.exclude(pk=self.instance.pk)
        if repetidos.exists():
            raise serializers.ValidationError("Ya existe un conjunto con ese nombre.")
        return valor

    def validate_direccion(self, valor):
        return valor.strip()

    def validate(self, datos):
        return validar_color(datos)


class AcentoSerializer(serializers.Serializer):
    acento = serializers.ChoiceField(choices=Acento.choices)
    color = color_hex()

    def validate(self, datos):
        return validar_color(datos)


class LogoSerializer(serializers.Serializer):
    archivo = serializers.FileField()
