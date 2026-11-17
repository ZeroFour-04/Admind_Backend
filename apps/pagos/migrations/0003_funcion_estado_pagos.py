from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("pagos", "0002_comprobante"),
        ("unidades", "0002_estructura"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE FUNCTION fn_estado_pagos(
                    p_conjunto uuid,
                    p_periodo date
                )
                RETURNS TABLE (
                    unidad_id uuid,
                    unidad_nombre text,
                    estado text
                )
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    IF p_conjunto IS NULL THEN
                        RAISE EXCEPTION 'El conjunto es obligatorio.' USING ERRCODE = '22004';
                    END IF;
                    IF p_periodo IS NULL OR EXTRACT(DAY FROM p_periodo) <> 1 THEN
                        RAISE EXCEPTION 'El periodo debe ser el primer dia del mes.' USING ERRCODE = '22023';
                    END IF;

                    RETURN QUERY
                    SELECT
                        u.id,
                        u.nombre::text,
                        CASE
                            WHEN p.confirmado_por_id IS NOT NULL THEN 'CONFIRMADO'
                            WHEN p.reportado_por_id IS NOT NULL THEN 'REPORTADO'
                            ELSE 'SIN_REPORTE'
                        END::text
                    FROM unidades_unidad AS u
                    LEFT JOIN pagos_pagodeadministracion AS p
                        ON p.unidad_id = u.id
                        AND p.conjunto_id = u.conjunto_id
                        AND p.conjunto_id = p_conjunto
                        AND p.periodo = p_periodo
                    WHERE u.conjunto_id = p_conjunto
                    ORDER BY u.nombre;
                END;
                $$;
            """,
            reverse_sql="DROP FUNCTION fn_estado_pagos(uuid, date);",
        ),
    ]
