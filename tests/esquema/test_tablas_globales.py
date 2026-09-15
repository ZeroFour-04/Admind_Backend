"""Prueba transversal de tablas globales (maestro §5.4, R12).

Recorre las tablas reales de la base de pruebas: una tabla fuera de la lista cerrada sin
conjunto_id obligatorio hace fallar la suite.
"""
import pytest
from django.apps import apps
from django.db import connection, models

from apps.comun.aislamiento.managers import ManagerDeConjunto

pytestmark = pytest.mark.django_db

# Lista cerrada. Agregar una tabla aquí es una decisión de diseño, no un arreglo para que pase la prueba.
TABLAS_GLOBALES = {
    "personas_persona": "Persona: una sola en toda la plataforma",
    "cuentas_usuario": "Usuario: una cuenta por persona",
    "cuentas_usuario_groups": "la crea Django por PermissionsMixin; AdMind no usa grupos de Django",
    "cuentas_usuario_user_permissions": "la crea Django por PermissionsMixin; AdMind no usa esos permisos",
    "conjuntos_conjunto": "el conjunto mismo",
    "cuentas_tokendesesion": "sesión de un usuario; el conjunto activo cambia dentro de la misma sesión",
}

# Llevan conjunto_id, pero puede ser nulo.
TABLAS_CON_CONJUNTO_OPCIONAL = {
    "permisos_asignacion": "nulo solo para el Superusuario (maestro §5.3)",
}


def tablas_de_django():
    tablas = {"django_migrations"}
    for modelo in apps.get_models(include_auto_created=True):
        if modelo.__module__.startswith("django."):
            tablas.add(modelo._meta.db_table)
    return tablas


def tablas_sin_conjunto_obligatorio():
    omitidas = tablas_de_django() | set(TABLAS_GLOBALES)
    faltantes = []
    with connection.cursor() as cursor:
        for tabla in connection.introspection.table_names(cursor):
            if tabla in omitidas:
                continue
            columnas = {c.name: c for c in connection.introspection.get_table_description(cursor, tabla)}
            conjunto = columnas.get("conjunto_id")
            if conjunto is None or (conjunto.null_ok and tabla not in TABLAS_CON_CONJUNTO_OPCIONAL):
                faltantes.append(tabla)
    return faltantes


def test_toda_tabla_fuera_de_la_lista_cerrada_tiene_conjunto_id_obligatorio():
    assert tablas_sin_conjunto_obligatorio() == []


def test_la_revision_detecta_una_tabla_nueva_sin_conjunto_id():
    with connection.cursor() as cursor:
        cursor.execute("CREATE TABLE tabla_nueva_sin_conjunto (id uuid PRIMARY KEY)")
        cursor.execute("CREATE TABLE tabla_nueva_con_conjunto_nulo (id uuid PRIMARY KEY, conjunto_id uuid NULL)")

    faltantes = tablas_sin_conjunto_obligatorio()

    assert "tabla_nueva_sin_conjunto" in faltantes
    assert "tabla_nueva_con_conjunto_nulo" in faltantes


def test_todo_modelo_con_conjunto_filtra_por_conjunto_activo_y_admite_fk_compuesta():
    revisados = 0
    for modelo in apps.get_models():
        if modelo._meta.db_table in TABLAS_CON_CONJUNTO_OPCIONAL:
            continue
        if "conjunto" not in {campo.name for campo in modelo._meta.fields}:
            continue
        claves_unicas = {
            frozenset(restriccion.fields)
            for restriccion in modelo._meta.constraints
            if isinstance(restriccion, models.UniqueConstraint) and restriccion.condition is None
        }
        assert isinstance(modelo._default_manager, ManagerDeConjunto), modelo
        assert frozenset({"id", "conjunto"}) in claves_unicas, modelo
        revisados += 1

    assert revisados > 0
