from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone


class UserProfile(models.Model):
    class Role(models.TextChoices):
        STUDENT = 'student', 'Estudante'
        TEACHER = 'teacher', 'Professor(a)'

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
        verbose_name='usuario',
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.STUDENT,
        verbose_name='papel',
    )
    academic_id = models.CharField(
        max_length=30,
        blank=True,
        verbose_name='matricula',
    )
    cpf = models.CharField(
        max_length=14,
        blank=True,
        default='',
        verbose_name='cpf',
    )
    birth_date = models.DateField(
        null=True,
        blank=True,
        verbose_name='data de nascimento',
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        default='',
        verbose_name='telefone',
    )

    class Meta:
        verbose_name = 'perfil de usuario'
        verbose_name_plural = 'perfis de usuario'

    def __str__(self):
        return f'{self.user.get_username()} ({self.get_role_display()})'

    def ensure_academic_id(self, created_at=None):
        if self.role != self.Role.STUDENT or self.academic_id:
            return False

        effective_created_at = created_at or getattr(self.user, 'date_joined', None)
        self.academic_id = generate_academic_id(effective_created_at)
        return True


class Course(models.Model):
    code = models.CharField(
        max_length=20,
        unique=True,
        verbose_name='codigo',
    )
    title = models.CharField(
        max_length=150,
        verbose_name='titulo',
    )
    description = models.TextField(
        verbose_name='descricao',
    )
    syllabus = models.TextField(
        blank=True,
        verbose_name='ementa',
    )
    workload_hours = models.PositiveIntegerField(
        default=0,
        verbose_name='carga horaria',
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='courses_taught',
        verbose_name='professor',
    )
    is_published = models.BooleanField(
        default=False,
        verbose_name='publicado',
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='criado em',
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='atualizado em',
    )

    class Meta:
        verbose_name = 'curso'
        verbose_name_plural = 'cursos'
        ordering = ['title']

    def __str__(self):
        return f'{self.code} - {self.title}'

    def clean(self):
        super().clean()
        if not self.teacher_id:
            return
        if _user_role(self.teacher) != UserProfile.Role.TEACHER:
            raise ValidationError({'teacher': 'O responsavel pelo curso deve ser um professor.'})


class Enrollment(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pendente'
        ACTIVE = 'active', 'Ativa'
        COMPLETED = 'completed', 'Concluída'
        CANCELLED = 'cancelled', 'Cancelada'

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='enrollments',
        verbose_name='estudante',
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='enrollments',
        verbose_name='curso',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        verbose_name='status',
    )
    enrolled_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='matriculado em',
    )
    final_grade = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        verbose_name='nota final',
    )

    class Meta:
        verbose_name = 'matricula'
        verbose_name_plural = 'matriculas'
        constraints = [
            models.UniqueConstraint(fields=['student', 'course'], name='unique_student_enrollment'),
        ]
        ordering = ['-enrolled_at']

    def __str__(self):
        return f'{self.student} em {self.course}'

    def clean(self):
        super().clean()
        if _user_role(self.student) != UserProfile.Role.STUDENT:
            raise ValidationError({'student': 'A matricula deve estar vinculada a um estudante.'})


class Module(models.Model):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='modules',
        verbose_name='modulo',
    )
    title = models.CharField(
        max_length=150,
        verbose_name='titulo',
    )
    description = models.TextField(
        blank=True,
        default='',
        verbose_name='descricao',
    )
    order = models.PositiveIntegerField(
        default=1,
        verbose_name='ordem',
    )

    class Meta:
        verbose_name = 'modulo'
        verbose_name_plural = 'modulos'
        ordering = ['course', 'order', 'id']
        constraints = [
            models.UniqueConstraint(fields=['course', 'order'], name='unique_module_order_per_course'),
        ]

    def __str__(self):
        return f'{self.course.code} - {self.title}'


class CourseItem(models.Model):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='course_items',
        verbose_name='curso',
    )
    module = models.ForeignKey(
        Module,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='course_items',
        verbose_name='modulo',
    )
    title = models.CharField(
        max_length=150,
        verbose_name='titulo',
    )
    description = models.TextField(
        verbose_name='descricao',
    )
    is_published = models.BooleanField(
        default=False,
        verbose_name='publicado',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='course_items_created',
        verbose_name='criado por',
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='criado em',
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='atualizado em',
    )

    class Meta:
        verbose_name = 'item do curso'
        verbose_name_plural = 'itens do curso'
        ordering = ['title', 'id']

    def __str__(self):
        return f'{self.title} ({self.course.code})'

    @property
    def kind(self):
        if isinstance(self, ResourceItem):
            return 'resource'
        if isinstance(self, AssignmentItem):
            return 'assignment'
        if isinstance(self, QuizItem):
            return 'quiz'
        if isinstance(self, ForumItem):
            return 'forum'

        for attr, value in (
            ('resourceitem', 'resource'),
            ('assignmentitem', 'assignment'),
            ('quizitem', 'quiz'),
            ('forumitem', 'forum'),
        ):
            try:
                getattr(self, attr)
                return value
            except ObjectDoesNotExist:
                continue
        return 'course_item'

    @property
    def kind_label(self):
        return {
            'resource': 'Material',
            'assignment': 'Tarefa',
            'quiz': 'Quiz',
            'forum': 'Fórum',
        }.get(self.kind, 'Item')

    @property
    def detail_object(self):
        if isinstance(self, (ResourceItem, AssignmentItem, QuizItem, ForumItem)):
            return self

        for attr in ('resourceitem', 'assignmentitem', 'quizitem', 'forumitem'):
            try:
                return getattr(self, attr)
            except ObjectDoesNotExist:
                continue
        return self

    def clean(self):
        super().clean()
        errors = {}

        if not self.created_by_id:
            errors['created_by'] = 'O item do curso deve ser associado ao usuário criador.'
        elif _user_role(self.created_by) != UserProfile.Role.TEACHER:
            errors['created_by'] = 'O item do curso deve ser criado por um professor.'

        if self.module and self.module.course_id != self.course_id:
            errors['module'] = 'O modulo precisa pertencer ao mesmo curso do item.'

        if errors:
            raise ValidationError(errors)


class ResourceItem(CourseItem):
    attachment_url = models.URLField(
        blank=True,
        verbose_name='link do material',
    )
    attachment_file = models.FileField(
        upload_to='course_item_resources/',
        blank=True,
        null=True,
        verbose_name='arquivo do material',
    )

    class Meta:
        verbose_name = 'material'
        verbose_name_plural = 'materiais'

    def clean(self):
        super().clean()
        if not (self.attachment_url or self.attachment_file):
            raise ValidationError('Informe um link ou envie um arquivo para o material.')


class AssignmentItem(CourseItem):
    due_date = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='data limite',
    )
    max_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        verbose_name='nota maxima',
    )
    statement_url = models.URLField(
        blank=True,
        verbose_name='link do enunciado',
    )
    statement_file = models.FileField(
        upload_to='assignment_statements/',
        blank=True,
        null=True,
        verbose_name='arquivo do enunciado',
    )

    class Meta:
        verbose_name = 'tarefa'
        verbose_name_plural = 'tarefas'
        ordering = ['due_date', 'title']


class QuizItem(CourseItem):
    due_date = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='prazo',
    )
    max_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        verbose_name='nota maxima',
    )
    allow_resubmissions = models.BooleanField(
        default=True,
        verbose_name='permite reenviar respostas',
    )

    class Meta:
        verbose_name = 'quiz'
        verbose_name_plural = 'quizzes'
        ordering = ['due_date', 'title']


class ForumItem(CourseItem):
    class Meta:
        verbose_name = 'forum'
        verbose_name_plural = 'foruns'


class QuizQuestion(models.Model):
    class QuestionType(models.TextChoices):
        SINGLE_CHOICE = 'single_choice', 'Uma resposta'
        MULTIPLE_CHOICE = 'multiple_choice', 'Múltiplas respostas'

    quiz = models.ForeignKey(
        QuizItem,
        on_delete=models.CASCADE,
        related_name='questions',
        verbose_name='quiz',
    )
    statement = models.TextField(
        verbose_name='enunciado',
    )
    image = models.FileField(
        upload_to='quiz_question_images/',
        blank=True,
        null=True,
        verbose_name='imagem da questao',
    )
    question_type = models.CharField(
        max_length=30,
        choices=QuestionType.choices,
        default=QuestionType.SINGLE_CHOICE,
        verbose_name='tipo de questao',
    )
    order = models.PositiveIntegerField(
        default=1,
        verbose_name='ordem',
    )
    weight = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=1,
        validators=[MinValueValidator(0)],
        verbose_name='peso',
    )

    class Meta:
        verbose_name = 'questao de quiz'
        verbose_name_plural = 'questoes de quiz'
        ordering = ['order', 'id']
        constraints = [
            models.UniqueConstraint(fields=['quiz', 'order'], name='unique_quiz_question_order'),
        ]

    def __str__(self):
        return f'{self.quiz.title} · Questão {self.order}'


class QuizOption(models.Model):
    question = models.ForeignKey(
        QuizQuestion,
        on_delete=models.CASCADE,
        related_name='options',
        verbose_name='questao',
    )
    text = models.CharField(
        max_length=255,
        verbose_name='texto',
    )
    is_correct = models.BooleanField(
        default=False,
        verbose_name='correta',
    )
    order = models.PositiveIntegerField(
        default=1,
        verbose_name='ordem',
    )

    class Meta:
        verbose_name = 'alternativa'
        verbose_name_plural = 'alternativas'
        ordering = ['order', 'id']
        constraints = [
            models.UniqueConstraint(fields=['question', 'order'], name='unique_quiz_option_order'),
        ]

    def __str__(self):
        return f'{self.question} · Alternativa {self.order}'


class ForumMessage(models.Model):
    forum = models.ForeignKey(
        ForumItem,
        on_delete=models.CASCADE,
        related_name='messages',
        verbose_name='forum',
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='forum_messages',
        verbose_name='autor',
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='replies',
        verbose_name='resposta a',
    )
    content = models.TextField(
        verbose_name='mensagem',
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='criada em',
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='atualizada em',
    )

    class Meta:
        verbose_name = 'mensagem do forum'
        verbose_name_plural = 'mensagens do forum'
        ordering = ['created_at', 'id']

    def __str__(self):
        return f'{self.author} em {self.forum.title}'

    def clean(self):
        super().clean()
        errors = {}

        if self.parent and self.parent.forum_id != self.forum_id:
            errors['parent'] = 'A resposta precisa pertencer ao mesmo fórum.'

        if self.author_id and _user_role(self.author) not in (UserProfile.Role.STUDENT, UserProfile.Role.TEACHER):
            errors['author'] = 'A mensagem precisa estar vinculada a um usuário válido.'

        if errors:
            raise ValidationError(errors)


class Submission(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Rascunho'
        SUBMITTED = 'submitted', 'Enviada'
        REVIEWED = 'reviewed', 'Avaliada'
        LATE = 'late', 'Enviada com atraso'

    assignment = models.ForeignKey(
        AssignmentItem,
        on_delete=models.CASCADE,
        related_name='submissions',
        verbose_name='tarefa',
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='submissions',
        verbose_name='estudante',
    )
    content = models.TextField(
        blank=True,
        verbose_name='conteudo',
    )
    attachment_file = models.FileField(
        upload_to='assignment_submissions/',
        blank=True,
        null=True,
        verbose_name='arquivo enviado',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name='status',
    )
    submitted_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='enviada em',
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='atualizada em',
    )
    score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        verbose_name='nota',
    )
    feedback = models.TextField(
        blank=True,
        verbose_name='feedback',
    )
    graded_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='avaliada em',
    )
    graded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='graded_submissions',
        verbose_name='avaliada por',
    )

    class Meta:
        verbose_name = 'entrega'
        verbose_name_plural = 'entregas'
        ordering = ['-updated_at']
        constraints = [
            models.UniqueConstraint(fields=['assignment', 'student'], name='unique_submission_per_assignment_student'),
        ]

    def __str__(self):
        student_label = self.student if self.student_id else 'Sem estudante'
        assignment_label = self.assignment if self.assignment_id else 'Sem tarefa'
        return f'{student_label} - {assignment_label}'

    def clean(self):
        super().clean()
        errors = {}

        if self.student_id and _user_role(self.student) != UserProfile.Role.STUDENT:
            errors['student'] = 'A entrega deve estar vinculada a um estudante.'

        if self.graded_by and _user_role(self.graded_by) != UserProfile.Role.TEACHER:
            errors['graded_by'] = 'A correcao deve ser feita por um professor.'

        if (
            self.score is not None
            and self.assignment_id
            and self.assignment.max_score is not None
            and self.score > self.assignment.max_score
        ):
            errors['score'] = 'A nota nao pode ser maior que a nota maxima da tarefa.'

        if not self.content and not self.attachment_file:
            errors['content'] = 'Envie um arquivo ou preencha uma descrição da entrega.'

        if errors:
            raise ValidationError(errors)


class Answer(models.Model):
    quiz = models.ForeignKey(
        QuizItem,
        on_delete=models.CASCADE,
        related_name='answers',
        verbose_name='quiz',
    )
    question = models.ForeignKey(
        QuizQuestion,
        on_delete=models.CASCADE,
        related_name='answers',
        verbose_name='questao',
    )
    selected_option = models.ForeignKey(
        QuizOption,
        on_delete=models.CASCADE,
        related_name='answers',
        verbose_name='alternativa marcada',
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='quiz_answers',
        verbose_name='estudante',
    )
    answered_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='respondida em',
    )

    class Meta:
        verbose_name = 'resposta de quiz'
        verbose_name_plural = 'respostas de quiz'
        ordering = ['-answered_at']
        constraints = [
            models.UniqueConstraint(
                fields=['question', 'student', 'selected_option'],
                name='unique_answer_per_question_student_option',
            ),
        ]

    def __str__(self):
        return f'{self.student} · {self.question}'

    def clean(self):
        super().clean()
        errors = {}

        if _user_role(self.student) != UserProfile.Role.STUDENT:
            errors['student'] = 'A resposta do quiz deve estar vinculada a um estudante.'

        if self.question_id and self.quiz_id and self.question.quiz_id != self.quiz_id:
            errors['question'] = 'A questão precisa pertencer ao quiz informado.'

        if self.selected_option_id and self.question_id and self.selected_option.question_id != self.question_id:
            errors['selected_option'] = 'A alternativa precisa pertencer à questão informada.'

        if errors:
            raise ValidationError(errors)


def _user_role(user):
    if user is None:
        return None
    profile = getattr(user, 'profile', None)
    return getattr(profile, 'role', None)


def generate_academic_id(created_at=None):
    year_suffix = (created_at or timezone.now()).strftime('%y')
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

    return f'{prefix}{next_sequence:07d}'


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        profile = UserProfile.objects.create(user=instance)
        if profile.ensure_academic_id(instance.date_joined):
            profile.save(update_fields=['academic_id'])
