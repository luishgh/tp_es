from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agora', '0015_quizitem_allow_resubmissions'),
    ]

    operations = [
        migrations.AddField(
            model_name='quizquestion',
            name='question_type',
            field=models.CharField(
                choices=[('single_choice', 'Uma resposta'), ('multiple_choice', 'Múltiplas respostas')],
                default='single_choice',
                max_length=30,
                verbose_name='tipo de questao',
            ),
        ),
        migrations.RemoveConstraint(
            model_name='answer',
            name='unique_answer_per_question_student',
        ),
        migrations.AddConstraint(
            model_name='answer',
            constraint=models.UniqueConstraint(
                fields=('question', 'student', 'selected_option'),
                name='unique_answer_per_question_student_option',
            ),
        ),
    ]
