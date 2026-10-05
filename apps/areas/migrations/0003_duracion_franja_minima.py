from django.db import migrations, models
from django.db.models import Q


def subir_duraciones_cortas(apps, schema_editor):
    Area = apps.get_model("areas", "Area")
    Area.objects.using(schema_editor.connection.alias).filter(duracion_franja_minutos__lt=120).update(
        duracion_franja_minutos=120
    )


class Migration(migrations.Migration):
    dependencies = [
        ("areas", "0002_quitar_clasificacion"),
    ]

    operations = [
        migrations.RunPython(subir_duraciones_cortas, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="area",
            name="area_duracion_franja_positiva",
        ),
        migrations.AddConstraint(
            model_name="area",
            constraint=models.CheckConstraint(
                condition=Q(duracion_franja_minutos__gte=120),
                name="area_duracion_franja_minima",
            ),
        ),
    ]
