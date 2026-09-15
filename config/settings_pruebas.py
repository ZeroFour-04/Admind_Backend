"""Ajustes para correr las pruebas: los de siempre más las tablas de apoyo de tests/aislamiento."""
from config.settings import *  # noqa: F403

INSTALLED_APPS = [*INSTALLED_APPS, "tests.aislamiento"]  # noqa: F405
