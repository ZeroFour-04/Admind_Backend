from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.conjuntos.serializers import ConjuntoResumenSerializer
from apps.cuentas import dos_factores
from apps.cuentas.models import Usuario
from apps.permisos.catalogo import ROLES_DE_CONJUNTO, Rol
from apps.permisos.servicios import permisos_efectivos
from apps.personas.models import Persona, TipoDocumento, normalizar_documento


def estado_de_la_sesion(sesion):
    conjunto = sesion.conjunto_activo
    return {
        "conjunto_activo": ConjuntoResumenSerializer(conjunto).data if conjunto else None,
        "permisos": sorted(permisos_efectivos(sesion.usuario.persona, sesion.conjunto_activo_id)),
        "dos_factores": dos_factores.estado(sesion),
    }


class IniciarSesionSerializer(serializers.Serializer):
    correo = serializers.EmailField()
    contrasena = serializers.CharField(trim_whitespace=False, write_only=True)


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

    def validate(self, datos):
        # Una persona existe una sola vez en la plataforma (HU-04). Vincular a alguien que ya
        # existe es otra operación (HU-07), así que aquí solo se avisa.
        numero = normalizar_documento(datos["numero_documento"])
        if Persona.objects.filter(tipo_documento=datos["tipo_documento"], numero_documento=numero).exists():
            raise serializers.ValidationError(
                {"numero_documento": ["Ya existe una persona con este documento."]}
            )
        return datos


class UsuarioResumenSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    nombre = serializers.SerializerMethodField()
    correo = serializers.EmailField()
    tipo_documento = serializers.CharField(source="persona.tipo_documento")
    documento = serializers.CharField(source="persona.numero_documento")
    telefono = serializers.CharField(source="persona.telefono")
    activo = serializers.BooleanField(source="persona.activo")
    roles = serializers.SerializerMethodField()

    def get_nombre(self, usuario):
        return str(usuario.persona)

    def get_roles(self, usuario):
        """Sus roles en el conjunto activo; los de otros conjuntos no se muestran."""
        return [asignacion.get_rol_display() for asignacion in usuario.persona.asignaciones_en_conjunto]


class SolicitarRecuperacionSerializer(serializers.Serializer):
    correo = serializers.EmailField()


class RestablecerContrasenaSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    contrasena = serializers.CharField(trim_whitespace=False, write_only=True)


class CodigoSerializer(serializers.Serializer):
    codigo = serializers.CharField(max_length=20)
