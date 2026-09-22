"""Crea un conjunto de prueba y un usuario por rol del catálogo, para probar la plataforma en local.

No es parte de ninguna historia: arma el primer Superusuario, que la pantalla de usuarios no
puede crear, y una cuenta por cada rol de conjunto. Todas quedan con la misma contraseña, que se
pide al ejecutar. Se puede correr otra vez: lo que ya existe no se toca.
"""
from getpass import getpass

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.conjuntos.models import Conjunto
from apps.conjuntos.servicios import crear_conjunto
from apps.cuentas import servicios
from apps.cuentas.models import Usuario
from apps.permisos.catalogo import ROLES_DE_CONJUNTO, Rol
from apps.permisos.servicios import tiene_permisos_sensibles
from apps.personas.models import TipoDocumento

NOMBRE_DEL_CONJUNTO = "Conjunto de prueba"


class Command(BaseCommand):
    help = "Crea un conjunto de prueba y un usuario por rol, todos con la misma contraseña. Solo en local."

    def handle(self, *args, **opciones):
        if not settings.DEBUG:
            raise CommandError("Este comando es solo para pruebas en local, con DEBUG activo.")
        contrasena = self.pedir_contrasena()

        with transaction.atomic():
            # El Superusuario va primero: es quien crea el conjunto y no queda con rol dentro de él.
            superusuario = self.crear_usuario(Rol.SUPERUSUARIO, 1, contrasena, conjunto_id=None)
            conjunto = Conjunto.objects.filter(nombre=NOMBRE_DEL_CONJUNTO).first()
            if conjunto is None:
                conjunto = crear_conjunto(superusuario.persona, NOMBRE_DEL_CONJUNTO)
                self.stdout.write(f"Conjunto creado: {conjunto.nombre}")
            else:
                self.stdout.write(f"Conjunto ya existía: {conjunto.nombre}")

            roles_de_conjunto = [rol for rol in Rol if rol.value in ROLES_DE_CONJUNTO]
            for numero, rol in enumerate(roles_de_conjunto, start=2):
                self.crear_usuario(rol, numero, contrasena, conjunto_id=conjunto.id)

        self.stdout.write(self.style.SUCCESS("Listo. Las cuentas que dicen \"pide 2FA\" lo configuran al entrar."))

    def pedir_contrasena(self):
        """Como createsuperuser: se pide dos veces, sin mostrarla, hasta que cumpla las reglas."""
        while True:
            contrasena = getpass("Contraseña para todos los usuarios de prueba: ")
            if contrasena != getpass("Repítela: "):
                self.stderr.write("No coinciden. Otra vez.")
                continue
            try:
                validate_password(contrasena)
            except ValidationError as error:
                self.stderr.write("\n".join(error.messages))
                continue
            return contrasena

    def crear_usuario(self, rol, numero, contrasena, conjunto_id):
        correo = f"{rol.value}@example.com"
        usuario = Usuario.objects.select_related("persona").filter(correo=correo).first()
        if usuario is None:
            try:
                usuario = servicios.registrar_usuario(
                    conjunto_id,
                    tipo_documento=TipoDocumento.CC,
                    numero_documento=str(9000000000 + numero),
                    nombres="Prueba",
                    apellidos=rol.label,
                    correo=correo,
                    contrasena=contrasena,
                    rol=rol,
                )
            except servicios.PersonaYaExiste:
                raise CommandError(f"La cédula de prueba de {rol.label} ya es de otra persona.")
            estado = "creado"
        else:
            estado = "ya existía, no se tocó"

        segundo_factor = " · pide 2FA" if tiene_permisos_sensibles(usuario.persona) else ""
        self.stdout.write(f"{rol.label:<15} {correo:<30} {estado}{segundo_factor}")
        return usuario
