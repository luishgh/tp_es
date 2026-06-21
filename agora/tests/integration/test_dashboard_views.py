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


class TeacherDashboardTests(TestCase):
    def setUp(self):
        user_model = get_user_model()

        self.teacher = user_model.objects.create_user(
            username='teacher-dashboard',
            password='test-pass-123',
            first_name='Téo',
            last_name='Professor',
            email='teo@example.com',
        )
        self.teacher.profile.role = UserProfile.Role.TEACHER
        self.teacher.profile.save(update_fields=['role'])

        self.student = user_model.objects.create_user(
            username='student-dashboard',
            password='test-pass-123',
            first_name='Ana',
            last_name='Estudante',
        )
        self.student.profile.role = UserProfile.Role.STUDENT
        self.student.profile.save(update_fields=['role'])

        self.course = Course.objects.create(
            code='DSA101',
            title='Estruturas de Dados',
            description='Conceitos de estruturas.',
            syllabus='Árvores e grafos.',
            workload_hours=60,
            teacher=self.teacher,
            is_published=True,
        )

    def _build_context(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse('agora:index'))
        self.assertEqual(response.status_code, 200)
        return response.context

    def test_teacher_dashboard_counts_progress_in_submissions_with_overdue_scope(self):
        now = timezone.now()

        future_submission = AssignmentItem.objects.create(
            course=self.course,
            title='Trabalho futuro',
            description='Prazo não vencido.',
            due_date=now + timedelta(hours=4),
            max_score=10,
            is_published=True,
            created_by=self.teacher,
        )
        overdue_pending = AssignmentItem.objects.create(
            course=self.course,
            title='Relatório vencido',
            description='Prazo vencido pendente.',
            due_date=now - timedelta(days=1),
            max_score=10,
            is_published=True,
            created_by=self.teacher,
        )
        overdue_reviewed = AssignmentItem.objects.create(
            course=self.course,
            title='Quizado vencido',
            description='Prazo vencido corrigido.',
            due_date=now - timedelta(days=2),
            max_score=10,
            is_published=True,
            created_by=self.teacher,
        )

        Submission.objects.create(
            assignment=future_submission,
            student=self.student,
            status=Submission.Status.SUBMITTED,
            content='Resposta futura',
        )
        Submission.objects.create(
            assignment=overdue_pending,
            student=self.student,
            status=Submission.Status.SUBMITTED,
            content='Resposta vencida',
        )
        Submission.objects.create(
            assignment=overdue_reviewed,
            student=self.student,
            status=Submission.Status.REVIEWED,
            content='Resposta corrigida',
            score=9,
            feedback='Bom trabalho',
            graded_by=self.teacher,
            graded_at=now - timedelta(hours=1),
        )

        context = self._build_context()
        card = context['courses_page'][0]

        self.assertEqual(card['progress'], 50)
        self.assertEqual(card['progress_label'], '1/2 submissões corrigidas')
        self.assertEqual(context['pending_count'], 1)
        self.assertNotIn(
            future_submission.id,
            [item['id'] for item in context['work_page']],
        )

    def test_teacher_dashboard_excludes_assignments_without_due_date_from_metrics(self):
        now = timezone.now()

        assignment_without_due_date = AssignmentItem.objects.create(
            course=self.course,
            title='Sem prazo',
            description='Atividade sem prazo.',
            due_date=None,
            max_score=10,
            is_published=True,
            created_by=self.teacher,
        )
        overdue_reviewed = AssignmentItem.objects.create(
            course=self.course,
            title='Com prazo vencido',
            description='Prazo vencido para contar.',
            due_date=now - timedelta(days=1),
            max_score=10,
            is_published=True,
            created_by=self.teacher,
        )

        Submission.objects.create(
            assignment=assignment_without_due_date,
            student=self.student,
            status=Submission.Status.REVIEWED,
            content='Sem prazo',
            score=8,
            feedback='Sem prazo',
            graded_by=self.teacher,
            graded_at=now - timedelta(hours=2),
        )
        Submission.objects.create(
            assignment=overdue_reviewed,
            student=self.student,
            status=Submission.Status.REVIEWED,
            content='Com prazo',
            score=9,
            feedback='Com prazo',
            graded_by=self.teacher,
            graded_at=now - timedelta(hours=1),
        )

        context = self._build_context()
        card = context['courses_page'][0]
        pending_cards = context['work_page']

        self.assertEqual(card['progress'], 100)
        self.assertEqual(card['progress_label'], '1/1 submissões corrigidas')
        self.assertEqual(len(pending_cards), 0)

class StudentDashboardIntegrationTests(AgoraTestDataMixin, TestCase):
    def setUp(self):
        self.teacher = self.create_user('dash-teacher-extra', UserProfile.Role.TEACHER)
        self.student = self.create_user('dash-student-extra', UserProfile.Role.STUDENT)
        self.course = self.create_course(code='DASH101', title='Dashboard Course', is_published=True)
        Enrollment.objects.create(student=self.student, course=self.course, status=Enrollment.Status.ACTIVE)

    def test_student_dashboard_counts_only_unsubmitted_assignments_and_unanswered_quizzes(self):
        now = timezone.now()
        submitted_assignment = AssignmentItem.objects.create(
            course=self.course,
            title='Ja enviada',
            description='Submetida.',
            due_date=now + timedelta(days=2),
            max_score=Decimal('10.00'),
            is_published=True,
            created_by=self.teacher,
        )
        overdue_assignment = AssignmentItem.objects.create(
            course=self.course,
            title='Atrasada',
            description='Pendente.',
            due_date=now - timedelta(days=1),
            max_score=Decimal('10.00'),
            is_published=True,
            created_by=self.teacher,
        )
        Submission.objects.create(
            assignment=submitted_assignment,
            student=self.student,
            status=Submission.Status.SUBMITTED,
            content='Resposta.',
        )
        quiz_data = self.create_quiz_with_questions(course=self.course, title='Quiz respondido')
        Answer.objects.create(
            quiz=quiz_data['quiz'],
            question=quiz_data['single'],
            selected_option=quiz_data['single_correct'],
            student=self.student,
        )
        pending_quiz = self.create_quiz_with_questions(course=self.course, title='Quiz pendente')['quiz']

        self.client.force_login(self.student)
        response = self.client.get(reverse('agora:index'))

        self.assertEqual(response.status_code, 200)
        pending_titles = [card['title'] for card in response.context['work_page']]
        self.assertIn(overdue_assignment.title, pending_titles)
        self.assertIn(pending_quiz.title, pending_titles)
        self.assertNotIn(submitted_assignment.title, pending_titles)
        self.assertNotIn(quiz_data['quiz'].title, pending_titles)
        self.assertEqual(response.context['pending_count'], 2)
        self.assertEqual(response.context['overdue_activities'], 1)
