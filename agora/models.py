from django.conf import settings
from django.core.exceptions import ValidationError
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
    social_name = models.CharField(
        max_length=150,
        blank=True,
        default='',
        verbose_name='nome social',
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        default='',
        verbose_name='telefone',
    )
    bio = models.TextField(
        blank=True,
        default='',
        verbose_name='biografia',
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


class Activity(models.Model):
    class Type(models.TextChoices):
        ASSIGNMENT = 'assignment', 'Tarefa'
        QUIZ = 'quiz', 'Quiz'
        FORUM = 'forum', 'Fórum'
        POLL = 'poll', 'Enquete'

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='activities',
        verbose_name='curso',
    )
    title = models.CharField(
        max_length=150,
        verbose_name='titulo',
    )
    description = models.TextField(
        verbose_name='descricao',
    )
    activity_type = models.CharField(
        max_length=20,
        choices=Type.choices,
        default=Type.ASSIGNMENT,
        verbose_name='tipo',
    )
    due_date = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='prazo',
    )
    max_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=100,
        validators=[MinValueValidator(0)],
        verbose_name='nota maxima',
    )
    is_published = models.BooleanField(
        default=False,
        verbose_name='publicada',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='activities_created',
        verbose_name='criada por',
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
        verbose_name = 'atividade'
        verbose_name_plural = 'atividades'
        ordering = ['due_date', 'title']

    def __str__(self):
        return f'{self.title} ({self.course.code})'

    def clean(self):
        super().clean()
        errors = {}

        if _user_role(self.created_by) != UserProfile.Role.TEACHER:
            errors['created_by'] = 'A atividade deve ser criada por um professor.'

        if errors:
            raise ValidationError(errors)


class Submission(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Rascunho'
        SUBMITTED = 'submitted', 'Enviada'
        REVIEWED = 'reviewed', 'Avaliada'
        LATE = 'late', 'Enviada com atraso'

    activity = models.ForeignKey(
        Activity,
        on_delete=models.CASCADE,
        related_name='submissions',
        verbose_name='atividade',
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
    attachment_url = models.URLField(
        blank=True,
        verbose_name='link do anexo',
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
            models.UniqueConstraint(fields=['activity', 'student'], name='unique_submission_per_activity_student'),
        ]

    def __str__(self):
        return f'{self.student} - {self.activity}'

    def clean(self):
        super().clean()
        errors = {}

        if _user_role(self.student) != UserProfile.Role.STUDENT:
            errors['student'] = 'A entrega deve estar vinculada a um estudante.'

        if self.graded_by and _user_role(self.graded_by) != UserProfile.Role.TEACHER:
            errors['graded_by'] = 'A correcao deve ser feita por um professor.'

        if self.score is not None and self.score > self.activity.max_score:
            errors['score'] = 'A nota nao pode ser maior que a nota maxima da atividade.'

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
