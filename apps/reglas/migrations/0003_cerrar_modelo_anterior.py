"""Cierra las reglas abiertas del modelo anterior (plan D4) y pasa el aforo de cada una a su área.

No borra nada: cada regla queda en el historial, cerrada hoy.
"""
from django.db import migrations
from django.db.models import DateField, F, Value
from django.db.models.functions import Greatest
from django.utils import timezone


def cerrar_modelo_anterior(apps, schema_editor):
    Regla = apps.get_model("reglas", "Regla")
    Area = apps.get_model("areas", "Area")
    abiertas = Regla.objects.filter(vigencia_hasta__isnull=True)

    # El aforo deja de ser regla: cada área se queda con el de su regla abierta, el menor si había varias.
    aforos = {}
    for regla in abiertas.filter(tipo="AFORO"):
        aforos[regla.area_id] = min(regla.parametros["maximo"], aforos.get(regla.area_id, 10000))
    for area_id, maximo in aforos.items():
        Area.objects.filter(pk=area_id).update(aforo_maximo=maximo)

    # Una regla que todavía no empezaba se cierra en su fecha de inicio, como hace `servicios.cerrar`.
    hoy = Value(timezone.localdate(), output_field=DateField())
    abiertas.update(vigencia_hasta=Greatest(F("vigencia_desde"), hoy))


class Migration(migrations.Migration):

    dependencies = [
        ("areas", "0004_aforo_maximo"),
        ("reglas", "0002_area_opcional"),
    ]

    operations = [
        migrations.RunPython(cerrar_modelo_anterior, migrations.RunPython.noop),
    ]
