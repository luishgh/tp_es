from django.db import migrations


def populate_student_academic_ids(apps, schema_editor):
    UserProfile = apps.get_model('agora', 'UserProfile')

    student_profiles = UserProfile.objects.select_related('user').filter(
        role='student',
        academic_id='',
    ).order_by('user__date_joined', 'id')

    for profile in student_profiles:
        year_suffix = profile.user.date_joined.strftime('%y')
        prefix = year_suffix
        next_sequence = 1

        existing_ids = UserProfile.objects.filter(
            academic_id__startswith=prefix,
        ).exclude(
            academic_id='',
        ).values_list('academic_id', flat=True)

        for academic_id in existing_ids:
            sequence_part = academic_id[len(prefix):]
            if len(sequence_part) == 7 and sequence_part.isdigit():
                next_sequence = max(next_sequence, int(sequence_part) + 1)

        profile.academic_id = f'{prefix}{next_sequence:07d}'
        profile.save(update_fields=['academic_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('agora', '0004_alter_enrollment_status'),
    ]

    operations = [
        migrations.RunPython(populate_student_academic_ids, migrations.RunPython.noop),
    ]
