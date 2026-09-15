import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class UsuarioManager(BaseUserManager):
    def create_user(self, correo, password, persona, **campos):
        if not correo:
            raise ValueError("El usuario necesita un correo.")
        usuario = self.model(correo=correo, persona=persona, **campos)
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_superuser(self, correo, password, persona, **campos):
        campos["is_staff"] = True
        campos["is_superuser"] = True
        return self.create_user(correo, password, persona, **campos)

    def get_by_natural_key(self, correo):
        return self.get(correo=correo.strip().lower())


class Usuario(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    persona = models.OneToOneField(
        "personas.Persona",
        on_delete=models.PROTECT,
        related_name="usuario",
    )
    correo = models.EmailField(max_length=254, unique=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    creado_en = models.DateTimeField(auto_now_add=True)

    objects = UsuarioManager()

    USERNAME_FIELD = "correo"
    EMAIL_FIELD = "correo"
    REQUIRED_FIELDS = ["persona"]

    def save(self, *args, **kwargs):
        self.correo = self.correo.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.correo


class TokenDeSesionManager(models.Manager):
    def vigente(self, huella):
        return (
            self.select_related("usuario__persona")
            .filter(huella=huella, vence_en__gt=timezone.now())
            .first()
        )


class TokenDeSesion(models.Model):
    """La sesión de un usuario en la API (maestro §12.7 b).

    El token viaja en cada petición; aquí solo se guarda su huella, como con las contraseñas.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    usuario = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name="tokens")
    huella = models.CharField(max_length=64, unique=True)
    # Lo fija el selector de conjunto (HU-26). Ninguna petición lo trae como parámetro.
    conjunto_activo = models.ForeignKey(
        "conjuntos.Conjunto",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    dos_factores_verificado = models.BooleanField(default=False)
    creado_en = models.DateTimeField(auto_now_add=True)
    vence_en = models.DateTimeField()

    objects = TokenDeSesionManager()

    def __str__(self):
        return f"{self.usuario} · vence {self.vence_en:%Y-%m-%d %H:%M}"