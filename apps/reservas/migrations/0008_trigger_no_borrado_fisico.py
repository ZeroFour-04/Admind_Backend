from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("reservas", "0007_procedimiento_expirar_bloqueos"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE FUNCTION bloquear_borrado_solicitud()
                RETURNS trigger
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    RAISE EXCEPTION 'No se permite el borrado fisico de una solicitud de reserva.'
                        USING ERRCODE = '23514';
                    RETURN OLD;
                END;
                $$;

                CREATE TRIGGER trg_sin_borrado_fisico
                BEFORE DELETE ON reservas_solicitud
                FOR EACH ROW
                EXECUTE FUNCTION bloquear_borrado_solicitud();
            """,
            reverse_sql="""
                DROP TRIGGER trg_sin_borrado_fisico ON reservas_solicitud;
                DROP FUNCTION bloquear_borrado_solicitud();
            """,
        ),
    ]
