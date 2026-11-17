from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("ingresos", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE FUNCTION fn_aforo_actual(p_conjunto uuid, p_area uuid)
                RETURNS integer
                LANGUAGE plpgsql
                AS $$
                DECLARE
                    cantidad integer;
                BEGIN
                    IF p_conjunto IS NULL THEN
                        RAISE EXCEPTION 'El conjunto es obligatorio.' USING ERRCODE = '22004';
                    END IF;
                    IF p_area IS NULL OR NOT EXISTS (
                        SELECT 1
                        FROM areas_area AS a
                        WHERE a.id = p_area
                            AND a.conjunto_id = p_conjunto
                    ) THEN
                        RAISE EXCEPTION 'El area no existe en el conjunto.' USING ERRCODE = 'P0002';
                    END IF;

                    SELECT COALESCE(SUM(1 + i.acompanantes), 0)::integer
                    INTO cantidad
                    FROM ingresos_ingreso AS i
                    WHERE i.conjunto_id = p_conjunto
                        AND i.area_id = p_area
                        AND i.estado = 'ADENTRO';

                    RETURN cantidad;
                END;
                $$;
            """,
            reverse_sql="DROP FUNCTION fn_aforo_actual(uuid, uuid);",
        ),
    ]
