from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("areas", "0003_duracion_franja_minima"),
    ]

    operations = [
        # Las áreas que ya existen reciben 1: un valor a la vista, que obliga a escribir el real.
        migrations.AddField(
            model_name="area",
            name="aforo_maximo",
            field=models.PositiveSmallIntegerField(default=1),
            preserve_default=False,
        ),
        migrations.AddConstraint(
            model_name="area",
            constraint=models.CheckConstraint(
                condition=models.Q(("aforo_maximo__gte", 1)), name="area_aforo_maximo_valido"
            ),
        ),
    ]
