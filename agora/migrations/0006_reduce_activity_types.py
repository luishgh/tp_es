from django.db import migrations, models


def convert_legacy_activity_types(apps, schema_editor):
    Activity = apps.get_model('agora', 'Activity')
    Activity.objects.filter(activity_type__in=['quiz', 'forum', 'poll']).update(activity_type='assignment')


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('agora', '0005_activity_attachment_url_alter_activity_activity_type_and_more'),
    ]

    operations = [
        migrations.RunPython(convert_legacy_activity_types, reverse_code=noop_reverse),
        migrations.AlterField(
            model_name='activity',
            name='activity_type',
            field=models.CharField(
                choices=[('assignment', 'Tarefa'), ('resource', 'Material')],
                default='assignment',
                max_length=20,
                verbose_name='tipo',
            ),
        ),
    ]

