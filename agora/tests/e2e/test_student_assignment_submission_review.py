from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from agora.models import AssignmentItem, Course, Enrollment, Module, Submission, UserProfile


class StudentAssignmentSubmissionReviewE2ETests(TestCase):
    password = 'test-pass-123'

    def setUp(self):
        user_model = get_user_model()
        self.teacher = user_model.objects.create_user(
            username='assignment-teacher',
            password=self.password,
            first_name='Ada',
            last_name='Lovelace',
            email='assignment-teacher@example.com',
        )
        self.teacher.profile.role = UserProfile.Role.TEACHER
        self.teacher.profile.academic_id = ''
        self.teacher.profile.save(update_fields=['role', 'academic_id'])

        self.student = user_model.objects.create_user(
            username='assignment-student',
            password=self.password,
            first_name='Grace',
            last_name='Hopper',
            email='assignment-student@example.com',
        )
        self.student.profile.role = UserProfile.Role.STUDENT
        self.student.profile.ensure_academic_id(self.student.date_joined)
        self.student.profile.save(update_fields=['role', 'academic_id'])

        self.course = Course.objects.create(
            code='E2E303',
            title='Assignment Flow Course',
            description='Course used by an end-to-end assignment submission test.',
            syllabus='Assignments, review, and feedback.',
            workload_hours=60,
            teacher=self.teacher,
            is_published=True,
        )
        self.module = Module.objects.create(
            course=self.course,
            title='Entregas',
            description='Módulo com tarefas avaliativas.',
            order=1,
        )
        self.assignment = AssignmentItem.objects.create(
            course=self.course,
            module=self.module,
            title='Entrega E2E',
            description='Resolva a tarefa pelo fluxo completo.',
            statement_url='https://example.com/assignment-e2e.pdf',
            due_date=timezone.now() + timedelta(days=5),
            max_score=Decimal('10.00'),
            is_published=True,
            created_by=self.teacher,
        )
        Enrollment.objects.create(
            student=self.student,
            course=self.course,
            status=Enrollment.Status.ACTIVE,
        )

    def test_student_submits_assignment_teacher_reviews_and_student_sees_feedback(self):
        student_login_response = self.client.post(
            reverse('agora:login'),
            data={
                'action': 'login',
                'username': self.student.username,
                'password': self.password,
            },
        )

        self.assertEqual(student_login_response.status_code, 302)
        self.assertEqual(student_login_response.url, reverse('agora:index'))
        self.assertEqual(int(self.client.session['_auth_user_id']), self.student.id)

        dashboard_response = self.client.get(reverse('agora:index'))

        self.assertEqual(dashboard_response.status_code, 200)
        self.assertContains(dashboard_response, self.assignment.title)

        course_detail_response = self.client.get(reverse('agora:course_detail', args=[self.course.id]))

        self.assertEqual(course_detail_response.status_code, 200)
        self.assertContains(course_detail_response, self.assignment.title)

        assignment_detail_response = self.client.get(reverse('agora:course_item_detail', args=[self.assignment.id]))

        self.assertEqual(assignment_detail_response.status_code, 200)
        self.assertContains(assignment_detail_response, 'Não iniciado')
        self.assertContains(assignment_detail_response, 'Registrar entrega')

        submit_response = self.client.post(
            reverse('agora:course_item_detail', args=[self.assignment.id]),
            data={
                'action': 'submit_assignment',
                'content': 'Minha entrega textual para a tarefa E2E.',
            },
        )

        self.assertEqual(submit_response.status_code, 302)
        self.assertEqual(submit_response.url, reverse('agora:course_item_detail', args=[self.assignment.id]))

        submission = Submission.objects.get(assignment=self.assignment, student=self.student)
        self.assertEqual(submission.status, Submission.Status.SUBMITTED)
        self.assertIsNotNone(submission.submitted_at)

        submitted_detail_response = self.client.get(reverse('agora:course_item_detail', args=[self.assignment.id]))

        self.assertEqual(submitted_detail_response.status_code, 200)
        self.assertContains(submitted_detail_response, 'Enviada')
        self.assertContains(submitted_detail_response, 'Tarefa enviada')
        self.assertContains(submitted_detail_response, 'Minha entrega textual para a tarefa E2E.')

        updated_dashboard_response = self.client.get(reverse('agora:index'))

        self.assertEqual(updated_dashboard_response.status_code, 200)
        self.assertNotContains(updated_dashboard_response, self.assignment.title)

        student_logout_response = self.client.post(reverse('agora:logout'))

        self.assertEqual(student_logout_response.status_code, 302)
        self.assertNotIn('_auth_user_id', self.client.session)

        teacher_login_response = self.client.post(
            reverse('agora:login'),
            data={
                'action': 'login',
                'username': self.teacher.username,
                'password': self.password,
            },
        )

        self.assertEqual(teacher_login_response.status_code, 302)
        self.assertEqual(teacher_login_response.url, reverse('agora:index'))
        self.assertEqual(int(self.client.session['_auth_user_id']), self.teacher.id)

        teacher_assignment_response = self.client.get(reverse('agora:course_item_detail', args=[self.assignment.id]))

        self.assertEqual(teacher_assignment_response.status_code, 200)
        self.assertContains(teacher_assignment_response, self.student.get_full_name())
        self.assertContains(teacher_assignment_response, 'Enviada')

        review_response = self.client.post(
            reverse('agora:submission_review', args=[submission.id]),
            data={
                'score': '8.50',
                'feedback': 'Boa entrega. Revise apenas a conclusão.',
            },
        )

        self.assertEqual(review_response.status_code, 302)
        self.assertEqual(review_response.url, reverse('agora:course_item_detail', args=[self.assignment.id]))

        submission.refresh_from_db()
        self.assertEqual(submission.status, Submission.Status.REVIEWED)
        self.assertEqual(submission.score, Decimal('8.50'))
        self.assertEqual(submission.feedback, 'Boa entrega. Revise apenas a conclusão.')
        self.assertEqual(submission.graded_by, self.teacher)
        self.assertIsNotNone(submission.graded_at)

        teacher_logout_response = self.client.post(reverse('agora:logout'))

        self.assertEqual(teacher_logout_response.status_code, 302)
        self.assertNotIn('_auth_user_id', self.client.session)

        student_relogin_response = self.client.post(
            reverse('agora:login'),
            data={
                'action': 'login',
                'username': self.student.username,
                'password': self.password,
            },
        )

        self.assertEqual(student_relogin_response.status_code, 302)
        self.assertEqual(student_relogin_response.url, reverse('agora:index'))
        self.assertEqual(int(self.client.session['_auth_user_id']), self.student.id)

        reviewed_detail_response = self.client.get(reverse('agora:course_item_detail', args=[self.assignment.id]))

        self.assertEqual(reviewed_detail_response.status_code, 200)
        self.assertContains(reviewed_detail_response, 'Avaliada')
        self.assertContains(reviewed_detail_response, 'Feedback:')
        self.assertContains(reviewed_detail_response, 'Boa entrega. Revise apenas a conclusão.')
        self.assertContains(reviewed_detail_response, 'Nota:')
        self.assertContains(reviewed_detail_response, '8.50')
