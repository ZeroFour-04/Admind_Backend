from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("infracciones", "0002_trigger_no_borrado_fisico"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE FUNCTION impedir_edicion_infraccion_anulada()
                RETURNS trigger
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    IF OLD.anulado THEN
                        RAISE EXCEPTION 'Un registro de infraccion anulado es inmutable.'
                            USING ERRCODE = '23514';
                    END IF;
                    RETURN NEW;
                END;
                $$;

                CREATE TRIGGER trg_infraccion_anulada_inmutable
                BEFORE UPDATE ON infracciones_registrodeinfraccion
                FOR EACH ROW
                EXECUTE FUNCTION impedir_edicion_infraccion_anulada();
            """,
            reverse_sql="""
                DROP TRIGGER trg_infraccion_anulada_inmutable ON infracciones_registrodeinfraccion;
                DROP FUNCTION impedir_edicion_infraccion_anulada();
            """,
        ),
    ]
