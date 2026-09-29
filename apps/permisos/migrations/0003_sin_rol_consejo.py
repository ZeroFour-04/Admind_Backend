from django.db import migrations, models


def borrar_asignaciones_de_consejo(apps, schema_editor):
    """El rol sale del catálogo: sus asignaciones no pueden seguir existiendo bajo la restricción nueva."""
    Asignacion = apps.get_model("permisos", "Asignacion")
    Asignacion.objects.filter(rol="consejo").delete()


class Migration(migrations.Migration):

    dependencies = [
        ('permisos', '0002_un_rol_por_conjunto'),
    ]

    operations = [
        migrations.RunPython(borrar_asignaciones_de_consejo, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name='asignacion',
            name='asignacion_conjunto_segun_alcance',
        ),
        migrations.AlterField(
            model_name='asignacion',
            name='rol',
            field=models.CharField(choices=[('superusuario', 'Superusuario'), ('administracion', 'Administración'), ('secretaria', 'Secretaría'), ('vigilancia', 'Vigilancia'), ('residente', 'Residente')], max_length=30),
        ),
        migrations.AddConstraint(
            model_name='asignacion',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('conjunto__isnull', True), ('rol__in', ['superusuario'])), models.Q(('conjunto__isnull', False), ('rol__in', ['administracion', 'residente', 'secretaria', 'vigilancia'])), _connector='OR'), name='asignacion_conjunto_segun_alcance'),
        ),
    ]
