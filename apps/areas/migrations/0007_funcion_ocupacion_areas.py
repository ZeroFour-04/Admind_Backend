from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("areas", "0006_area_condiciones_alquiler"),
        ("reservas", "0006_categoria_de_rechazo"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE FUNCTION fn_ocupacion_areas(
                    p_conjunto uuid,
                    p_desde date,
                    p_hasta date
                )
                RETURNS TABLE (
                    area_id uuid,
                    area_nombre text,
                    reservas bigint,
                    horas_reservadas numeric
                )
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    IF p_conjunto IS NULL THEN
                        RAISE EXCEPTION 'El conjunto es obligatorio.' USING ERRCODE = '22004';
                    END IF;
                    IF p_desde IS NULL OR p_hasta IS NULL OR p_desde > p_hasta THEN
                        RAISE EXCEPTION 'El rango de fechas no es valido.' USING ERRCODE = '22023';
                    END IF;

                    RETURN QUERY
                    SELECT
                        a.id,
                        a.nombre::text,
                        COUNT(s.id)::bigint,
                        COALESCE(
                            ROUND(SUM(EXTRACT(EPOCH FROM (s.hora_fin - s.hora_inicio)) / 3600), 2),
                            0
                        )::numeric
                    FROM areas_area AS a
                    LEFT JOIN reservas_solicitud AS s
                        ON s.area_id = a.id
                        AND s.conjunto_id = a.conjunto_id
                        AND s.conjunto_id = p_conjunto
                        AND s.estado = 'RESERVADA'
                        AND s.fecha BETWEEN p_desde AND p_hasta
                    WHERE a.conjunto_id = p_conjunto
                        AND a.modo_uso = 'reserva'
                    GROUP BY a.id, a.nombre
                    ORDER BY a.nombre;
                END;
                $$;
            """,
            reverse_sql="DROP FUNCTION fn_ocupacion_areas(uuid, date, date);",
        ),
    ]
