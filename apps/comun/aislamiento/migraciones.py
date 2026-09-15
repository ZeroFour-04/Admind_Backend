from django.db import migrations

LARGO_MAXIMO_POSTGRESQL = 63


def fk_compuesta(tabla, columna, tabla_referida):
    """FK (columna, conjunto_id) contra (id, conjunto_id) de la tabla referida (maestro §7.1).

    Django no sabe que existe; PostgreSQL sí, y rechaza la fila que apunta a otro conjunto.
    La tabla referida necesita UNIQUE (id, conjunto), que ya trae ModeloDeConjunto.
    """
    nombre = f"{tabla}_{columna}_conjunto_fk"
    if len(nombre) > LARGO_MAXIMO_POSTGRESQL:
        raise ValueError(f"PostgreSQL recortaría el nombre de la restricción: {nombre}")
    return migrations.RunSQL(
        sql=(
            f'ALTER TABLE "{tabla}" ADD CONSTRAINT "{nombre}" '
            f'FOREIGN KEY ("{columna}", "conjunto_id") '
            f'REFERENCES "{tabla_referida}" ("id", "conjunto_id") ON DELETE RESTRICT'
        ),
        reverse_sql=f'ALTER TABLE "{tabla}" DROP CONSTRAINT "{nombre}"',
    )
