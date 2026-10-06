from rest_framework import serializers


class SubirReglamentoSerializer(serializers.Serializer):
    archivo = serializers.FileField()


class ReglamentoSerializer(serializers.Serializer):
    nombre = serializers.CharField()
    peso = serializers.IntegerField()
    subido_en = serializers.DateTimeField()
    subido_por = serializers.SerializerMethodField()

    def get_subido_por(self, reglamento):
        return str(reglamento.subido_por)
