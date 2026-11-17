from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("pagos", "0003_funcion_estado_pagos"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE FUNCTION bloquear_borrado_pago_administracion()
                RETURNS trigger
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    RAISE EXCEPTION 'No se permite el borrado fisico de un pago de administracion.'
                        USING ERRCODE = '23514';
                    RETURN OLD;
                END;
                $$;

                CREATE TRIGGER trg_sin_borrado_fisico
                BEFORE DELETE ON pagos_pagodeadministracion
                FOR EACH ROW
                EXECUTE FUNCTION bloquear_borrado_pago_administracion();
            """,
            reverse_sql="""
                DROP TRIGGER trg_sin_borrado_fisico ON pagos_pagodeadministracion;
                DROP FUNCTION bloquear_borrado_pago_administracion();
            """,
        ),
    ]
