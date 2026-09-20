from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password

from apps.cuentas.models import Usuario
from apps.personas.models import Persona, TipoDocumento
from apps.conjuntos.models import Conjunto
from apps.permisos.catalogo import ROLES_DE_CONJUNTO, Rol


class IniciarSesionSerializer(serializers.Serializer):
    correo = serializers.EmailField()
    contrasena = serializers.CharField(trim_whitespace=False, write_only=True)


class ConjuntoResumenSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    nombre = serializers.CharField()


class ConjuntoListaSerializer(ConjuntoResumenSerializer):
    direccion = serializers.CharField()


class CrearConjuntoSerializer(serializers.Serializer):
    nombre = serializers.CharField(max_length=80)
    direccion = serializers.CharField(max_length=200, allow_blank=True, required=False)

    def validate_nombre(self, valor):
        valor = valor.strip()
        if not valor:
            raise serializers.ValidationError("El nombre del conjunto es obligatorio.")
        if Conjunto.objects.filter(nombre__iexact=valor, activo=True).exists():
            raise serializers.ValidationError("Ya existe un conjunto con ese nombre.")
        return valor


class ElegirConjuntoSerializer(serializers.Serializer):
    conjunto = serializers.UUIDField()


class CrearUsuarioSerializer(serializers.Serializer):
    tipo_documento = serializers.ChoiceField(choices=TipoDocumento.choices)
    numero_documento = serializers.CharField(max_length=20)
    nombres = serializers.CharField(max_length=80)
    apellidos = serializers.CharField(max_length=80)
    telefono = serializers.CharField(max_length=16, allow_blank=True, required=False)
    correo = serializers.EmailField()
    contrasena = serializers.CharField(write_only=True, trim_whitespace=False)
    rol = serializers.ChoiceField(
        choices=[choice for choice in Rol.choices if choice[0] in ROLES_DE_CONJUNTO]
    )

    def validate_correo(self, valor):
        if Usuario.objects.filter(correo=valor.strip().lower()).exists():
            raise serializers.ValidationError("Ya existe un usuario con este correo.")
        return valor

    def validate_contrasena(self, valor):
        validate_password(valor)
        return valor


class UsuarioResumenSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    nombre = serializers.SerializerMethodField()
    correo = serializers.EmailField()
    tipo_documento = serializers.CharField(source="persona.tipo_documento")
    documento = serializers.CharField(source="persona.numero_documento")
    telefono = serializers.CharField(source="persona.telefono")
    activo = serializers.BooleanField(source="persona.activo")

    def get_nombre(self, usuario):
        return str(usuario.persona)
