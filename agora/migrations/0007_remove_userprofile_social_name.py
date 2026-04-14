from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('agora', '0006_userprofile_personal_fields'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='userprofile',
            name='social_name',
        ),
    ]

