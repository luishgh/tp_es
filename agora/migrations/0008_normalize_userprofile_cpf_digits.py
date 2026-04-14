import re

from django.db import migrations


def normalize_userprofile_cpf_digits(apps, schema_editor):
    UserProfile = apps.get_model('agora', 'UserProfile')

    for profile in UserProfile.objects.exclude(cpf='').only('id', 'cpf'):
        digits = re.sub(r'\\D', '', profile.cpf or '')
        if digits != profile.cpf:
            profile.cpf = digits
            profile.save(update_fields=['cpf'])


class Migration(migrations.Migration):

    dependencies = [
        ('agora', '0007_remove_userprofile_social_name'),
    ]

    operations = [
        migrations.RunPython(normalize_userprofile_cpf_digits, migrations.RunPython.noop),
    ]

