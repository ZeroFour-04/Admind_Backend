from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("casos", "0005_funcion_resumen_casos"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE FUNCTION bloquear_borrado_caso()
                RETURNS trigger
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    RAISE EXCEPTION 'No se permite el borrado fisico de un caso.'
                        USING ERRCODE = '23514';
                    RETURN OLD;
                END;
                $$;

                CREATE TRIGGER trg_sin_borrado_fisico
                BEFORE DELETE ON casos_caso
                FOR EACH ROW
                EXECUTE FUNCTION bloquear_borrado_caso();
            """,
            reverse_sql="""
                DROP TRIGGER trg_sin_borrado_fisico ON casos_caso;
                DROP FUNCTION bloquear_borrado_caso();
            """,
        ),
    ]
