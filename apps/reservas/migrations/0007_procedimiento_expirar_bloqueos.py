from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("reservas", "0006_categoria_de_rechazo"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE PROCEDURE sp_expirar_bloqueos_vencidos(p_conjunto uuid)
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    IF p_conjunto IS NULL THEN
                        RAISE EXCEPTION 'El conjunto es obligatorio.' USING ERRCODE = '22004';
                    END IF;

                    UPDATE reservas_solicitud
                    SET estado = 'EXPIRADA'
                    WHERE conjunto_id = p_conjunto
                        AND estado = 'EN_SOLICITUD'
                        AND bloqueo_vence_en <= CURRENT_TIMESTAMP;
                END;
                $$;
            """,
            reverse_sql="DROP PROCEDURE sp_expirar_bloqueos_vencidos(uuid);",
        ),
    ]
