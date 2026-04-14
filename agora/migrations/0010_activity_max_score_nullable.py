from django.db import migrations, models
import django.core.validators


def normalize_resource_fields(apps, schema_editor):
    Activity = apps.get_model('agora', 'Activity')
    Activity.objects.filter(activity_type='resource').update(max_score=None, due_date=None)


class Migration(migrations.Migration):

    dependencies = [
        ('agora', '0009_merge_20260414_1545'),
    ]

    operations = [
        migrations.RunPython(normalize_resource_fields, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='activity',
            name='max_score',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=5,
                null=True,
                validators=[django.core.validators.MinValueValidator(0)],
                verbose_name='nota maxima',
            ),
        ),
    ]

