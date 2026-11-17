from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("infracciones", "0001_registro_de_infraccion"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE FUNCTION bloquear_borrado_infraccion()
                RETURNS trigger
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    RAISE EXCEPTION 'No se permite el borrado fisico de una infraccion.'
                        USING ERRCODE = '23514';
                    RETURN OLD;
                END;
                $$;

                CREATE TRIGGER trg_sin_borrado_fisico
                BEFORE DELETE ON infracciones_registrodeinfraccion
                FOR EACH ROW
                EXECUTE FUNCTION bloquear_borrado_infraccion();
            """,
            reverse_sql="""
                DROP TRIGGER trg_sin_borrado_fisico ON infracciones_registrodeinfraccion;
                DROP FUNCTION bloquear_borrado_infraccion();
            """,
        ),
    ]
