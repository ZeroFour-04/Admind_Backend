from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("casos", "0004_ciclo_del_caso"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE FUNCTION fn_resumen_casos(p_conjunto uuid)
                RETURNS TABLE (
                    estado text,
                    prioridad text,
                    total bigint
                )
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    IF p_conjunto IS NULL THEN
                        RAISE EXCEPTION 'El conjunto es obligatorio.' USING ERRCODE = '22004';
                    END IF;

                    RETURN QUERY
                    SELECT c.estado::text, c.prioridad::text, COUNT(*)::bigint
                    FROM casos_caso AS c
                    WHERE c.conjunto_id = p_conjunto
                    GROUP BY c.estado, c.prioridad
                    ORDER BY c.estado, c.prioridad;
                END;
                $$;
            """,
            reverse_sql="DROP FUNCTION fn_resumen_casos(uuid);",
        ),
    ]
