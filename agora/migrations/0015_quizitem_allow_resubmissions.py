from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agora', '0014_courseitem_inheritance_refactor'),
    ]

    operations = [
        migrations.AddField(
            model_name='quizitem',
            name='allow_resubmissions',
            field=models.BooleanField(default=True, verbose_name='permite reenviar respostas'),
        ),
    ]
