from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agora', '0005_populate_student_academic_ids'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='birth_date',
            field=models.DateField(blank=True, null=True, verbose_name='data de nascimento'),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='cpf',
            field=models.CharField(blank=True, default='', max_length=14, verbose_name='cpf'),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='phone',
            field=models.CharField(blank=True, default='', max_length=20, verbose_name='telefone'),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='social_name',
            field=models.CharField(blank=True, default='', max_length=150, verbose_name='nome social'),
        ),
    ]
