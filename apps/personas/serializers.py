from rest_framework import serializers

from apps.permisos.catalogo import ROLES_DE_CONJUNTO, Rol
from apps.personas.models import TipoDocumento


class BuscarPersonaSerializer(serializers.Serializer):
    tipo_documento = serializers.ChoiceField(choices=TipoDocumento.choices)
    numero_documento = serializers.CharField(max_length=20)


class VincularPersonaSerializer(serializers.Serializer):
    persona = serializers.UUIDField()
    rol = serializers.ChoiceField(choices=[choice for choice in Rol.choices if choice[0] in ROLES_DE_CONJUNTO])
