import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


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