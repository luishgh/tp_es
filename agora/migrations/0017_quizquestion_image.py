from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agora', '0016_quiz_question_type_and_multi_answer'),
    ]

    operations = [
        migrations.AddField(
            model_name='quizquestion',
            name='image',
            field=models.FileField(blank=True, null=True, upload_to='quiz_question_images/', verbose_name='imagem da questao'),
        ),
    ]
