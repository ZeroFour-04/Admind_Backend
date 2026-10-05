from rest_framework import serializers

from apps.anuncios import servicios
from apps.anuncios.models import MAXIMO_DE_FOTOS, Alcance


class PublicarAnuncioSerializer(serializers.Serializer):
    titulo = serializers.CharField(max_length=120)
    cuerpo = serializers.CharField(max_length=4000)
    # Solo dos alcances. El alcance «persona» no existe (maestro §5.7).
    alcance = serializers.ChoiceField(choices=Alcance.choices)
    unidad = serializers.UUIDField(required=False, allow_null=True)
    # Opcionales. Aquí solo se cuentan: si cada archivo sirve como foto lo dice el servicio.
    fotos = serializers.ListField(child=serializers.FileField(allow_empty_file=True), required=False)

    def validate_fotos(self, fotos):
        if len(fotos) > MAXIMO_DE_FOTOS:
            raise serializers.ValidationError(f"Un anuncio lleva hasta {MAXIMO_DE_FOTOS} fotos.")
        return fotos

    def validate(self, datos):
        if datos["alcance"] == Alcance.VIVIENDA and not datos.get("unidad"):
            raise serializers.ValidationError({"unidad": ["Elige la vivienda a la que va el anuncio."]})
        if datos["alcance"] == Alcance.CONJUNTO and datos.get("unidad"):
            raise serializers.ValidationError({"unidad": ["Un anuncio para todo el conjunto no lleva vivienda."]})
        return datos


class EditarAnuncioSerializer(serializers.Serializer):
    titulo = serializers.CharField(max_length=120, required=False)
    cuerpo = serializers.CharField(max_length=4000, required=False)

    def validate(self, datos):
        # Cambiar a quién va sería avisar a otras personas, y el aviso ya salió al publicar.
        if {"alcance", "unidad"} & set(self.initial_data):
            raise serializers.ValidationError("El alcance de un anuncio no cambia después de publicarlo.")
        # Las fotos se suben al publicar y quedan fijas, igual que el alcance.
        if "fotos" in self.initial_data:
            raise serializers.ValidationError("Las fotos de un anuncio no cambian después de publicarlo.")
        return datos


class AnuncioSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    titulo = serializers.CharField()
    cuerpo = serializers.CharField()
    fotos = serializers.SerializerMethodField()
    alcance = serializers.CharField()
    unidad = serializers.SerializerMethodField()
    autor = serializers.SerializerMethodField()
    publicado_en = serializers.DateTimeField()
    editado_en = serializers.DateTimeField()
    puede_editar = serializers.SerializerMethodField()

    def get_fotos(self, anuncio):
        # Solo los ids, en orden. La imagen se pide aparte, en /anuncios/<id>/fotos/<foto>/.
        return [foto.id for foto in anuncio.fotos.all()]

    def get_autor(self, anuncio):
        return str(anuncio.autor)

    def get_unidad(self, anuncio):
        return {"id": anuncio.unidad.id, "nombre": anuncio.unidad.nombre} if anuncio.unidad else None

    def get_puede_editar(self, anuncio):
        return servicios.puede_editar(self.context["persona"], self.context["permisos"], anuncio)
