from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone

from agora.models import Course, QuizItem, QuizOption, QuizQuestion, UserProfile


class AgoraTestDataMixin:
    password = 'test-pass-123'

    def create_user(self, username, role=UserProfile.Role.STUDENT, **kwargs):
        user_model = get_user_model()
        user = user_model.objects.create_user(
            username=username,
            password=kwargs.pop('password', self.password),
            first_name=kwargs.pop('first_name', username.title()),
            last_name=kwargs.pop('last_name', 'User'),
            email=kwargs.pop('email', f'{username}@example.com'),
            **kwargs,
        )
        user.profile.role = role
        if role == UserProfile.Role.STUDENT:
            user.profile.ensure_academic_id(user.date_joined)
            update_fields = ['role', 'academic_id']
        else:
            user.profile.academic_id = ''
            update_fields = ['role', 'academic_id']
        user.profile.save(update_fields=update_fields)
        return user

    def create_course(self, teacher=None, code='TST101', title='Test Course', is_published=True):
        teacher = teacher or self.teacher
        return Course.objects.create(
            code=code,
            title=title,
            description='Course used by automated tests.',
            syllabus='Testing syllabus.',
            workload_hours=60,
            teacher=teacher,
            is_published=is_published,
        )

    def create_quiz_with_questions(self, course=None, module=None, title='Quiz base'):
        course = course or self.course
        quiz = QuizItem.objects.create(
            course=course,
            module=module,
            title=title,
            description='Quiz for tests.',
            due_date=timezone.now() + timedelta(days=2),
            max_score=Decimal('10.00'),
            allow_resubmissions=True,
            is_published=True,
            created_by=course.teacher,
        )
        question = QuizQuestion.objects.create(
            quiz=quiz,
            statement='Pergunta objetiva?',
            question_type=QuizQuestion.QuestionType.SINGLE_CHOICE,
            order=1,
            weight=Decimal('4.00'),
        )
        correct = QuizOption.objects.create(question=question, text='Correta', is_correct=True, order=1)
        wrong = QuizOption.objects.create(question=question, text='Incorreta', is_correct=False, order=2)
        multi = QuizQuestion.objects.create(
            quiz=quiz,
            statement='Pergunta multipla?',
            question_type=QuizQuestion.QuestionType.MULTIPLE_CHOICE,
            order=2,
            weight=Decimal('6.00'),
        )
        multi_correct_a = QuizOption.objects.create(question=multi, text='A', is_correct=True, order=1)
        multi_wrong = QuizOption.objects.create(question=multi, text='B', is_correct=False, order=2)
        multi_correct_c = QuizOption.objects.create(question=multi, text='C', is_correct=True, order=3)
        return {
            'quiz': quiz,
            'single': question,
            'single_correct': correct,
            'single_wrong': wrong,
            'multi': multi,
            'multi_correct_a': multi_correct_a,
            'multi_wrong': multi_wrong,
            'multi_correct_c': multi_correct_c,
        }
