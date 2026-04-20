from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from random import choice, randint

from agora.models import (
    Answer,
    AssignmentItem,
    Course,
    ForumItem,
    Enrollment,
    Module,
    QuizItem,
    QuizOption,
    QuizQuestion,
    ResourceItem,
    Submission,
    UserProfile,
)

User = get_user_model()


class Command(BaseCommand):
    help = "Popula o banco com dados ricos (nova versão)"

    def handle(self, *args, **kwargs):
        self.stdout.write("Criando dados...")

        now = timezone.now()

        # =========================
        # USERS
        # =========================
        def create_user(username, role):
            user, _ = User.objects.get_or_create(username=username)
            user.set_password('123456')
            user.save()

            profile = user.profile
            profile.role = role
            profile.ensure_academic_id(user.date_joined)
            profile.save()

            return user

        teacher1 = create_user('prof_ana', UserProfile.Role.TEACHER)
        teacher2 = create_user('prof_carlos', UserProfile.Role.TEACHER)

        students = [
            create_user('joao', UserProfile.Role.STUDENT),
            create_user('maria', UserProfile.Role.STUDENT),
            create_user('pedro', UserProfile.Role.STUDENT),
        ]

        # =========================
        # COURSES
        # =========================
        courses_data = [
            ('CS101', 'Intro à Programação', teacher1, 60),
            ('BD201', 'Banco de Dados', teacher2, 80),
            ('AL203', 'Algoritmos', teacher1, 80),
        ]

        courses = []

        for code, title, teacher, workload in courses_data:
            course, _ = Course.objects.get_or_create(
                code=code,
                defaults={
                    'title': title,
                    'description': f'Curso de {title}',
                    'syllabus': f'Ementa detalhada de {title}',
                    'workload_hours': workload,
                    'teacher': teacher,
                    'is_published': True,
                }
            )
            courses.append(course)

        # =========================
        # ENROLLMENTS
        # =========================
        for course in courses:
            for student in students:
                Enrollment.objects.get_or_create(
                    student=student,
                    course=course,
                    defaults={
                        'status': choice([
                            Enrollment.Status.ACTIVE,
                            Enrollment.Status.COMPLETED,
                        ]),
                        'final_grade': Decimal(randint(60, 100)) / 10,
                    }
                )

        # =========================
        # MODULES
        # =========================
        modules_by_course = {}

        for course in courses:
            modules = []
            for i in range(1, 4):
                module, _ = Module.objects.get_or_create(
                    course=course,
                    order=i,
                    defaults={
                        'title': f'Módulo {i}',
                        'description': f'Conteúdo do módulo {i}',
                    }
                )
                modules.append(module)
            modules_by_course[course.id] = modules

        # =========================
        # ACTIVITIES
        # =========================
        activity_templates = [
            ('Tarefa', 'assignment', 100),
            ('Quiz', 'quiz', None),
            ('Fórum', 'forum', None),
            ('Material', 'resource', None),
        ]

        all_activities = []

        for course in courses:
            modules = modules_by_course[course.id]

            for i in range(1, 7):
                name, activity_type, max_score = choice(activity_templates)
                module = choice(modules)

                bucket = choice(['past', 'soon', 'future'])

                if bucket == 'past':
                    due_date = now - timedelta(days=randint(1, 10))
                elif bucket == 'soon':
                    due_date = now + timedelta(days=randint(1, 3))
                else:
                    due_date = now + timedelta(days=randint(5, 15))

                title = f'{name} {i}'

                if activity_type == 'assignment':
                    activity, _ = AssignmentItem.objects.get_or_create(
                        course=course,
                        title=title,
                        defaults={
                            'module': module,
                            'description': f'{name} {i} do curso {course.title}',
                            'due_date': due_date,
                            'max_score': Decimal(max_score),
                            'statement_url': 'https://example.com/enunciado.pdf',
                            'is_published': True,
                            'created_by': course.teacher,
                        }
                    )
                elif activity_type == 'quiz':
                    activity, created = QuizItem.objects.get_or_create(
                        course=course,
                        title=title,
                        defaults={
                            'module': module,
                            'description': f'{name} {i} do curso {course.title}',
                            'due_date': due_date,
                            'max_score': Decimal('20'),
                            'is_published': True,
                            'created_by': course.teacher,
                        }
                    )
                    if created and not activity.questions.exists():
                        for question_order in range(1, 3):
                            question = QuizQuestion.objects.create(
                                quiz=activity,
                                statement=f'Pergunta {question_order} do {title}',
                                order=question_order,
                            )
                            for option_order in range(1, 5):
                                QuizOption.objects.create(
                                    question=question,
                                    text=f'Alternativa {option_order}',
                                    order=option_order,
                                    is_correct=option_order == 1,
                                )
                elif activity_type == 'forum':
                    activity, _ = ForumItem.objects.get_or_create(
                        course=course,
                        title=title,
                        defaults={
                            'module': module,
                            'description': f'{name} {i} do curso {course.title}',
                            'is_published': True,
                            'created_by': course.teacher,
                        }
                    )
                else:
                    activity, _ = ResourceItem.objects.get_or_create(
                        course=course,
                        title=title,
                        defaults={
                            'module': module,
                            'description': f'{name} {i} do curso {course.title}',
                            'attachment_url': 'https://example.com/material.pdf',
                            'is_published': True,
                            'created_by': course.teacher,
                        }
                    )

                all_activities.append(activity)

        # =========================
        # SUBMISSIONS
        # =========================
        for activity in all_activities:
            if isinstance(activity, ResourceItem) or isinstance(activity, ForumItem):
                continue

            for student in students:
                if randint(0, 1) == 0:
                    continue

                if isinstance(activity, AssignmentItem):
                    status = choice([
                        Submission.Status.SUBMITTED,
                        Submission.Status.REVIEWED,
                        Submission.Status.LATE,
                    ])

                    score = None
                    graded_by = None
                    graded_at = None

                    if status == Submission.Status.REVIEWED and activity.max_score:
                        max_score = int(activity.max_score)
                        score = Decimal(randint(int(max_score * 0.5), max_score))
                        graded_by = activity.created_by
                        graded_at = now - timedelta(hours=randint(1, 48))

                    Submission.objects.get_or_create(
                        assignment=activity,
                        student=student,
                        defaults={
                            'content': f'Resposta de {student.username}',
                            'status': status,
                            'submitted_at': now - timedelta(days=randint(0, 5)),
                            'score': score,
                            'feedback': 'Bom trabalho!' if score else '',
                            'graded_by': graded_by,
                            'graded_at': graded_at,
                        }
                    )
                elif isinstance(activity, QuizItem) and not Answer.objects.filter(quiz=activity, student=student).exists():
                    for question in activity.questions.all():
                        selected = question.options.order_by('?').first()
                        if selected:
                            Answer.objects.create(
                                quiz=activity,
                                question=question,
                                selected_option=selected,
                                student=student,
                            )

        self.stdout.write(self.style.SUCCESS("Dados criados com sucesso!"))
