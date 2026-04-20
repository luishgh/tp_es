from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


def migrate_activity_data_to_subclasses(apps, schema_editor):
    CourseItem = apps.get_model('agora', 'CourseItem')
    ResourceItem = apps.get_model('agora', 'ResourceItem')
    AssignmentItem = apps.get_model('agora', 'AssignmentItem')
    QuizItem = apps.get_model('agora', 'QuizItem')
    ForumItem = apps.get_model('agora', 'ForumItem')
    Submission = apps.get_model('agora', 'Submission')
    connection = schema_editor.connection
    quote = connection.ops.quote_name

    resource_table = quote(ResourceItem._meta.db_table)
    assignment_table = quote(AssignmentItem._meta.db_table)
    quiz_table = quote(QuizItem._meta.db_table)
    forum_table = quote(ForumItem._meta.db_table)
    course_item_table = quote(CourseItem._meta.db_table)
    submission_table = quote(Submission._meta.db_table)

    with connection.cursor() as cursor:
        for item in CourseItem.objects.all().iterator():
            activity_type = getattr(item, 'legacy_activity_type', 'assignment')

            if activity_type == 'resource':
                cursor.execute(
                    f"INSERT INTO {resource_table} (courseitem_ptr_id, attachment_url, attachment_file) VALUES (%s, %s, %s)",
                    [item.id, item.legacy_attachment_url, item.legacy_attachment_file],
                )
            elif activity_type == 'quiz':
                cursor.execute(
                    f"INSERT INTO {quiz_table} (courseitem_ptr_id, due_date, max_score) VALUES (%s, %s, %s)",
                    [item.id, item.legacy_due_date, item.legacy_max_score],
                )
            elif activity_type == 'forum':
                cursor.execute(
                    f"INSERT INTO {forum_table} (courseitem_ptr_id) VALUES (%s)",
                    [item.id],
                )
            else:
                cursor.execute(
                    f"""INSERT INTO {assignment_table}
                    (courseitem_ptr_id, due_date, max_score, statement_url, statement_file)
                    VALUES (%s, %s, %s, %s, %s)""",
                    [item.id, item.legacy_due_date, item.legacy_max_score, item.legacy_attachment_url, item.legacy_attachment_file],
                )

        cursor.execute(
            f"""
            DELETE FROM {submission_table}
            WHERE activity_id IN (
                SELECT id FROM {course_item_table}
                WHERE legacy_activity_type IN ('resource', 'quiz', 'forum')
            )
            """
        )


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ('agora', '0013_activity_attachment_file'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='Activity',
            new_name='CourseItem',
        ),
        migrations.AlterModelOptions(
            name='courseitem',
            options={
                'ordering': ['title', 'id'],
                'verbose_name': 'item do curso',
                'verbose_name_plural': 'itens do curso',
            },
        ),
        migrations.AlterField(
            model_name='courseitem',
            name='course',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='course_items', to='agora.course', verbose_name='curso'),
        ),
        migrations.AlterField(
            model_name='courseitem',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, verbose_name='criado em'),
        ),
        migrations.AlterField(
            model_name='courseitem',
            name='created_by',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='course_items_created', to=settings.AUTH_USER_MODEL, verbose_name='criado por'),
        ),
        migrations.AlterField(
            model_name='courseitem',
            name='is_published',
            field=models.BooleanField(default=False, verbose_name='publicado'),
        ),
        migrations.AlterField(
            model_name='courseitem',
            name='module',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='course_items', to='agora.module', verbose_name='modulo'),
        ),
        migrations.AlterField(
            model_name='courseitem',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, verbose_name='atualizado em'),
        ),
        migrations.RenameField(
            model_name='courseitem',
            old_name='activity_type',
            new_name='legacy_activity_type',
        ),
        migrations.RenameField(
            model_name='courseitem',
            old_name='attachment_file',
            new_name='legacy_attachment_file',
        ),
        migrations.RenameField(
            model_name='courseitem',
            old_name='attachment_url',
            new_name='legacy_attachment_url',
        ),
        migrations.RenameField(
            model_name='courseitem',
            old_name='due_date',
            new_name='legacy_due_date',
        ),
        migrations.RenameField(
            model_name='courseitem',
            old_name='max_score',
            new_name='legacy_max_score',
        ),
        migrations.CreateModel(
            name='AssignmentItem',
            fields=[
                ('courseitem_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='agora.courseitem')),
                ('due_date', models.DateTimeField(blank=True, null=True, verbose_name='data limite')),
                ('max_score', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True, validators=[MinValueValidator(0)], verbose_name='nota maxima')),
                ('statement_url', models.URLField(blank=True, verbose_name='link do enunciado')),
                ('statement_file', models.FileField(blank=True, null=True, upload_to='assignment_statements/', verbose_name='arquivo do enunciado')),
            ],
            options={
                'verbose_name': 'tarefa',
                'verbose_name_plural': 'tarefas',
                'ordering': ['due_date', 'title'],
            },
            bases=('agora.courseitem',),
        ),
        migrations.CreateModel(
            name='ForumItem',
            fields=[
                ('courseitem_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='agora.courseitem')),
            ],
            options={
                'verbose_name': 'forum',
                'verbose_name_plural': 'foruns',
            },
            bases=('agora.courseitem',),
        ),
        migrations.CreateModel(
            name='QuizItem',
            fields=[
                ('courseitem_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='agora.courseitem')),
                ('due_date', models.DateTimeField(blank=True, null=True, verbose_name='prazo')),
                ('max_score', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True, validators=[MinValueValidator(0)], verbose_name='nota maxima')),
            ],
            options={
                'verbose_name': 'quiz',
                'verbose_name_plural': 'quizzes',
                'ordering': ['due_date', 'title'],
            },
            bases=('agora.courseitem',),
        ),
        migrations.CreateModel(
            name='ResourceItem',
            fields=[
                ('courseitem_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='agora.courseitem')),
                ('attachment_url', models.URLField(blank=True, verbose_name='link do material')),
                ('attachment_file', models.FileField(blank=True, null=True, upload_to='course_item_resources/', verbose_name='arquivo do material')),
            ],
            options={
                'verbose_name': 'material',
                'verbose_name_plural': 'materiais',
            },
            bases=('agora.courseitem',),
        ),
        migrations.CreateModel(
            name='QuizQuestion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('statement', models.TextField(verbose_name='enunciado')),
                ('order', models.PositiveIntegerField(default=1, verbose_name='ordem')),
                ('weight', models.DecimalField(decimal_places=2, default=1, max_digits=5, validators=[MinValueValidator(0)], verbose_name='peso')),
                ('quiz', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='questions', to='agora.quizitem', verbose_name='quiz')),
            ],
            options={
                'verbose_name': 'questao de quiz',
                'verbose_name_plural': 'questoes de quiz',
                'ordering': ['order', 'id'],
            },
        ),
        migrations.CreateModel(
            name='QuizOption',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('text', models.CharField(max_length=255, verbose_name='texto')),
                ('is_correct', models.BooleanField(default=False, verbose_name='correta')),
                ('order', models.PositiveIntegerField(default=1, verbose_name='ordem')),
                ('question', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='options', to='agora.quizquestion', verbose_name='questao')),
            ],
            options={
                'verbose_name': 'alternativa',
                'verbose_name_plural': 'alternativas',
                'ordering': ['order', 'id'],
            },
        ),
        migrations.CreateModel(
            name='ForumMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('content', models.TextField(verbose_name='mensagem')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='criada em')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='atualizada em')),
                ('author', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='forum_messages', to=settings.AUTH_USER_MODEL, verbose_name='autor')),
                ('forum', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='agora.forumitem', verbose_name='forum')),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='replies', to='agora.forummessage', verbose_name='resposta a')),
            ],
            options={
                'verbose_name': 'mensagem do forum',
                'verbose_name_plural': 'mensagens do forum',
                'ordering': ['created_at', 'id'],
            },
        ),
        migrations.AddField(
            model_name='submission',
            name='attachment_file',
            field=models.FileField(blank=True, null=True, upload_to='assignment_submissions/', verbose_name='arquivo enviado'),
        ),
        migrations.RunPython(migrate_activity_data_to_subclasses, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name='submission',
            name='unique_submission_per_activity_student',
        ),
        migrations.RenameField(
            model_name='submission',
            old_name='activity',
            new_name='assignment',
        ),
        migrations.AlterField(
            model_name='submission',
            name='assignment',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='submissions', to='agora.assignmentitem', verbose_name='tarefa'),
        ),
        migrations.CreateModel(
            name='Answer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('answered_at', models.DateTimeField(auto_now_add=True, verbose_name='respondida em')),
                ('question', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='answers', to='agora.quizquestion', verbose_name='questao')),
                ('quiz', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='answers', to='agora.quizitem', verbose_name='quiz')),
                ('selected_option', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='answers', to='agora.quizoption', verbose_name='alternativa marcada')),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='quiz_answers', to=settings.AUTH_USER_MODEL, verbose_name='estudante')),
            ],
            options={
                'verbose_name': 'resposta de quiz',
                'verbose_name_plural': 'respostas de quiz',
                'ordering': ['-answered_at'],
            },
        ),
        migrations.RemoveField(
            model_name='courseitem',
            name='legacy_activity_type',
        ),
        migrations.RemoveField(
            model_name='courseitem',
            name='legacy_attachment_file',
        ),
        migrations.RemoveField(
            model_name='courseitem',
            name='legacy_attachment_url',
        ),
        migrations.RemoveField(
            model_name='courseitem',
            name='legacy_due_date',
        ),
        migrations.RemoveField(
            model_name='courseitem',
            name='legacy_max_score',
        ),
        migrations.RemoveField(
            model_name='submission',
            name='attachment_url',
        ),
        migrations.AddConstraint(
            model_name='quizquestion',
            constraint=models.UniqueConstraint(fields=('quiz', 'order'), name='unique_quiz_question_order'),
        ),
        migrations.AddConstraint(
            model_name='quizoption',
            constraint=models.UniqueConstraint(fields=('question', 'order'), name='unique_quiz_option_order'),
        ),
        migrations.AddConstraint(
            model_name='submission',
            constraint=models.UniqueConstraint(fields=('assignment', 'student'), name='unique_submission_per_assignment_student'),
        ),
        migrations.AddConstraint(
            model_name='answer',
            constraint=models.UniqueConstraint(fields=('question', 'student'), name='unique_answer_per_question_student'),
        ),
    ]
