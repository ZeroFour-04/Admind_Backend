import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """`Reglamento` pasa a ser `Documento` con `tipo` (HU-33, D3 a).

    Es un `RenameModel` y no un borrar-y-crear: la tabla se renombra (`ALTER TABLE … RENAME`) y los
    reglamentos que ya había quedan en ella, con `tipo = 'reglamento'`. Hay que hacer un respaldo de la base
    antes de aplicarla.
    """

    dependencies = [
        ('conjuntos', '0004_color_personalizado'),
        ('documentos', '0001_initial'),
        ('personas', '0001_initial'),
    ]

    operations = [
        migrations.RenameModel(old_name='Reglamento', new_name='Documento'),
        migrations.RemoveIndex(model_name='documento', name='reglamento_por_fecha'),
        migrations.RemoveConstraint(model_name='documento', name='documentos_reglamento_id_conjunto'),
        # Las filas que ya existen son todas reglamentos: ese es el valor con que se llena la columna nueva.
        migrations.AddField(
            model_name='documento',
            name='tipo',
            field=models.CharField(
                choices=[('reglamento', 'Reglamento de propiedad horizontal'), ('manual', 'Manual de convivencia')],
                default='reglamento',
                max_length=20,
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='documento',
            name='subido_por',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, related_name='documentos_subidos', to='personas.persona'
            ),
        ),
        migrations.AddIndex(
            model_name='documento',
            index=models.Index(fields=['conjunto', 'tipo', 'subido_en'], name='documento_por_tipo_y_fecha'),
        ),
        migrations.AddConstraint(
            model_name='documento',
            constraint=models.UniqueConstraint(fields=('id', 'conjunto'), name='documentos_documento_id_conjunto'),
        ),
        migrations.AddConstraint(
            model_name='documento',
            constraint=models.CheckConstraint(
                condition=models.Q(('tipo__in', ['reglamento', 'manual'])), name='documento_tipo_valido'
            ),
        ),
    ]
