"""Ajustes para correr las pruebas: los de siempre más las tablas y endpoints de apoyo de tests/aislamiento."""
from config.settings import *  # noqa: F403

INSTALLED_APPS = [*INSTALLED_APPS, "tests.aislamiento"]  # noqa: F405
ROOT_URLCONF = "config.urls_pruebas"

# Cifrado rápido e inseguro, solo para que la suite no tarde. Nunca en settings.py.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
