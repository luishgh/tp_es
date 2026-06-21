from decimal import Decimal
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from agora.models import AssignmentItem, Enrollment, Module, Submission, UserProfile
from agora.tests.playwright.base import PlaywrightTestCase


class AssignmentBrowserFlowTests(PlaywrightTestCase):
    def setUp(self):
        self.teacher = self.create_user('browser-teacher', UserProfile.Role.TEACHER)
        self.student = self.create_user('browser-student', UserProfile.Role.STUDENT)
        self.course = self.create_course(
            teacher=self.teacher,
            code='BROWSE303',
            title='Assignment Browser Flow',
            is_published=True,
        )
        self.module = Module.objects.create(
            course=self.course,
            title='Entregas',
            description='Módulo de atividades.',
            order=1,
        )
        self.assignment = AssignmentItem.objects.create(
            course=self.course,
            module=self.module,
            title='Entrega pelo navegador',
            description='Fluxo completo de submissão e correção.',
            statement_url='https://example.com/assignment-browser.pdf',
            due_date=timezone.now() + timedelta(days=5),
            max_score=Decimal('10.00'),
            is_published=True,
            created_by=self.teacher,
        )
        Enrollment.objects.create(student=self.student, course=self.course, status=Enrollment.Status.ACTIVE)

    def test_student_submits_assignment_and_teacher_reviews_it(self):
        with self.browser_page(user=self.student) as page:
            page.goto(self.live_server_url + reverse('agora:course_item_detail', args=[self.assignment.id]))
            page.get_by_text('Registrar entrega').wait_for()
            page.get_by_label('Observações da entrega').fill('Minha entrega textual para a tarefa via Playwright.')
            page.get_by_role('button', name='Registrar entrega').click()

            page.wait_for_url(self.live_server_url + reverse('agora:course_item_detail', args=[self.assignment.id]) + '**')
            page.get_by_role('heading', name='Tarefa enviada').wait_for()
            page.get_by_text('Minha entrega textual para a tarefa via Playwright.').wait_for()

        submission = Submission.objects.get(assignment=self.assignment, student=self.student)
        self.assertEqual(submission.status, Submission.Status.SUBMITTED)

        with self.browser_page(user=self.teacher) as page:
            page.goto(self.live_server_url + reverse('agora:submission_review', args=[submission.id]))
            page.get_by_label('Nota atribuída').fill('8.50')
            page.get_by_label('Feedback para o estudante').fill('Boa execução. Ajuste a conclusão.')
            page.get_by_role('button', name='Salvar avaliação').click()

            page.wait_for_url(self.live_server_url + reverse('agora:course_item_detail', args=[self.assignment.id]) + '**')

        submission.refresh_from_db()
        self.assertEqual(submission.status, Submission.Status.REVIEWED)
        self.assertEqual(submission.score, Decimal('8.50'))
        self.assertEqual(submission.feedback, 'Boa execução. Ajuste a conclusão.')
        self.assertEqual(submission.graded_by, self.teacher)

        with self.browser_page(user=self.student) as page:
            page.goto(self.live_server_url + reverse('agora:course_item_detail', args=[self.assignment.id]))
            page.get_by_text('Avaliada').wait_for()
            page.get_by_text('Boa execução. Ajuste a conclusão.').wait_for()
            page.get_by_text('8.50').wait_for()
