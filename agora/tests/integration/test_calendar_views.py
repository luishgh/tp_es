from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from agora.forms import (
    AssignmentCreateForm,
    AssignmentSubmissionForm,
    CourseCreateForm,
    ForumMessageForm,
    ModuleCreateForm,
    QuizCreateForm,
    ResourceCreateForm,
    SubmissionReviewForm,
    SuperuserCreateUserForm,
)
from agora.models import (
    Answer,
    AssignmentItem,
    Course,
    CourseItem,
    Enrollment,
    ForumItem,
    ForumMessage,
    Module,
    QuizItem,
    QuizOption,
    QuizQuestion,
    ResourceItem,
    Submission,
    UserProfile,
    generate_academic_id,
)
from agora.tests.helpers import AgoraTestDataMixin


class CalendarViewTests(TestCase):
    def setUp(self):
        user_model = get_user_model()

        self.teacher = user_model.objects.create_user(
            username='teacher01',
            password='test-pass-123',
            first_name='Ada',
            last_name='Lovelace',
            email='ada@example.com',
        )
        self.teacher.profile.role = UserProfile.Role.TEACHER
        self.teacher.profile.save(update_fields=['role'])

        self.student = user_model.objects.create_user(
            username='student01',
            password='test-pass-123',
            first_name='Grace',
            last_name='Hopper',
        )
        self.student.profile.role = UserProfile.Role.STUDENT
        self.student.profile.academic_id = '20260001'
        self.student.profile.save(update_fields=['role', 'academic_id'])

        self.course_a = Course.objects.create(
            code='MATH',
            title='Matemática',
            description='Curso de matemática.',
            syllabus='Cálculo.',
            workload_hours=60,
            teacher=self.teacher,
            is_published=True,
        )

        self.course_b = Course.objects.create(
            code='FIS',
            title='Física',
            description='Curso de física.',
            syllabus='Cinemática.',
            workload_hours=60,
            teacher=self.teacher,
            is_published=True,
        )

        Enrollment.objects.create(student=self.student, course=self.course_a, status=Enrollment.Status.ACTIVE)
        Enrollment.objects.create(student=self.student, course=self.course_b, status=Enrollment.Status.ACTIVE)

        due = timezone.now() + timedelta(hours=10)

        self.activity_alpha = AssignmentItem.objects.create(
            course=self.course_a,
            title='Alpha',
            description='Tarefa A.',
            due_date=due,
            max_score=10,
            is_published=True,
            created_by=self.teacher,
        )
        self.activity_beta = AssignmentItem.objects.create(
            course=self.course_a,
            title='Beta',
            description='Tarefa B.',
            due_date=due,
            max_score=10,
            is_published=True,
            created_by=self.teacher,
        )
        self.activity_gamma = AssignmentItem.objects.create(
            course=self.course_b,
            title='Gamma',
            description='Tarefa C.',
            due_date=due,
            max_score=10,
            is_published=True,
            created_by=self.teacher,
        )
        self.activity_delta = AssignmentItem.objects.create(
            course=self.course_b,
            title='Delta',
            description='Tarefa D.',
            due_date=due,
            max_score=10,
            is_published=True,
            created_by=self.teacher,
        )
        self.activity_sent = AssignmentItem.objects.create(
            course=self.course_b,
            title='Enviada',
            description='Tarefa enviada.',
            due_date=due,
            max_score=10,
            is_published=True,
            created_by=self.teacher,
        )

        Submission.objects.create(
            assignment=self.activity_sent,
            student=self.student,
            status=Submission.Status.SUBMITTED,
            content='Resposta',
        )

        self.grade_newest = AssignmentItem.objects.create(
            course=self.course_a,
            title='Atividade corrigida 1',
            description='Para nota',
            due_date=due,
            max_score=10,
            is_published=True,
            created_by=self.teacher,
        )
        self.grade_older = AssignmentItem.objects.create(
            course=self.course_a,
            title='Atividade corrigida 2',
            description='Para nota 2',
            due_date=due - timedelta(days=1),
            max_score=10,
            is_published=True,
            created_by=self.teacher,
        )
        self.grade_without_mark = AssignmentItem.objects.create(
            course=self.course_b,
            title='Corrigida sem data',
            description='Sem data',
            due_date=due,
            max_score=10,
            is_published=True,
            created_by=self.teacher,
        )

        Submission.objects.create(
            assignment=self.grade_newest,
            student=self.student,
            status=Submission.Status.REVIEWED,
            content='Resposta',
            score=9,
            feedback='Ótimo',
            graded_at=timezone.now() - timedelta(hours=1),
            graded_by=self.teacher,
        )
        Submission.objects.create(
            assignment=self.grade_older,
            student=self.student,
            status=Submission.Status.REVIEWED,
            content='Resposta',
            score=8,
            feedback='Bom',
            graded_at=timezone.now() - timedelta(days=2),
            graded_by=self.teacher,
        )
        Submission.objects.create(
            assignment=self.grade_without_mark,
            student=self.student,
            status=Submission.Status.REVIEWED,
            content='Resposta',
            score=7,
            feedback='Sem data',
        )

    def test_student_can_access_calendar(self):
        self.client.force_login(self.student)

        response = self.client.get(reverse('agora:calendar'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="calendar-prev-month"')
        self.assertContains(response, 'id="calendar-next-month"')
        self.assertContains(response, 'id="calendar-today-month"')

    def test_teacher_is_redirected_from_calendar(self):
        self.client.force_login(self.teacher)

        response = self.client.get(reverse('agora:calendar'))

        self.assertEqual(response.status_code, 302)

    def test_pending_agenda_is_top_three_sorted_by_date_and_course_code(self):
        self.client.force_login(self.student)

        response = self.client.get(reverse('agora:calendar'))
        agenda_items = response.context['agenda_items']

        self.assertEqual(len(agenda_items), 3)
        self.assertEqual(
            [item['title'] for item in agenda_items],
            ['Delta', 'Gamma', 'Alpha'],
        )
        self.assertNotIn('Enviada', [item['title'] for item in agenda_items])

    def test_grade_cards_are_ordered_by_most_recent_graded(self):
        self.client.force_login(self.student)

        response = self.client.get(reverse('agora:calendar'))
        grade_cards = response.context['grade_cards']

        self.assertEqual(len(grade_cards), 2)
        self.assertEqual(
            [grade['activity_title'] for grade in grade_cards],
            [self.grade_newest.title, self.grade_older.title],
        )

    def test_calendar_data_and_list_items_include_detail_links(self):
        self.client.force_login(self.student)

        response = self.client.get(reverse('agora:calendar'))
        agenda_items = response.context['agenda_items']
        grade_cards = response.context['grade_cards']

        for item in agenda_items:
            self.assertContains(response, reverse('agora:course_item_detail', args=[item['id']]))

        for grade in grade_cards:
            self.assertContains(response, reverse('agora:course_item_detail', args=[grade['id']]))

        calendar_items = response.context['calendar_items']
        self.assertTrue(all('detail_url' in item for item in calendar_items))

    def test_calendar_includes_quiz_items_marked_as_sent_when_answered(self):
        now = timezone.now()
        quiz_item = QuizItem.objects.create(
            course=self.course_a,
            title='Quiz enviado',
            description='Questionário do mês',
            due_date=now + timedelta(hours=11),
            max_score=10,
            is_published=True,
            created_by=self.teacher,
            allow_resubmissions=True,
        )
        question = QuizQuestion.objects.create(
            quiz=quiz_item,
            statement='Qual o tema da semana?',
            order=1,
            weight=1,
        )
        option = QuizOption.objects.create(
            question=question,
            text='Integração',
            is_correct=True,
            order=1,
        )
        Answer.objects.create(
            quiz=quiz_item,
            question=question,
            selected_option=option,
            student=self.student,
        )

        self.client.force_login(self.student)

        response = self.client.get(reverse('agora:calendar'))

        calendar_items = response.context['calendar_items']
        quiz_entry = next(item for item in calendar_items if item['id'] == quiz_item.id)
        self.assertEqual(quiz_entry['status_tone'], 'sent')
        self.assertContains(response, reverse('agora:course_item_detail', args=[quiz_item.id]))

class CalendarEmptyStateIntegrationTests(AgoraTestDataMixin, TestCase):
    def setUp(self):
        self.teacher = self.create_user('dash-teacher-extra', UserProfile.Role.TEACHER)
        self.student = self.create_user('dash-student-extra', UserProfile.Role.STUDENT)
        self.course = self.create_course(code='DASH101', title='Dashboard Course', is_published=True)
        Enrollment.objects.create(student=self.student, course=self.course, status=Enrollment.Status.ACTIVE)

    def test_calendar_without_active_enrollments_returns_empty_context(self):
        student_without_courses = self.create_user('dash-no-courses', UserProfile.Role.STUDENT)
        self.client.force_login(student_without_courses)

        response = self.client.get(reverse('agora:calendar'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['calendar_items'], [])
        self.assertEqual(response.context['agenda_items'], [])
        self.assertEqual(response.context['grade_cards'], [])
