from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from agora.models import Course, Enrollment, UserProfile


class StudentRegistrationEnrollmentLogoutE2ETests(TestCase):
    password = 'test-pass-123'

    def setUp(self):
        user_model = get_user_model()
        self.teacher = user_model.objects.create_user(
            username='e2e-teacher',
            password=self.password,
            first_name='Ada',
            last_name='Lovelace',
            email='teacher@example.com',
        )
        self.teacher.profile.role = UserProfile.Role.TEACHER
        self.teacher.profile.academic_id = ''
        self.teacher.profile.save(update_fields=['role', 'academic_id'])

        self.course = Course.objects.create(
            code='E2E101',
            title='End-to-End Course',
            description='Course used by an end-to-end student enrollment test.',
            syllabus='Registration, enrollment, and logout.',
            workload_hours=40,
            teacher=self.teacher,
            is_published=True,
        )

    def test_student_registers_requests_enrollment_and_logs_out(self):
        login_response = self.client.get(reverse('agora:login'))

        self.assertEqual(login_response.status_code, 200)

        register_response = self.client.post(
            reverse('agora:login'),
            data={
                'action': 'register',
                'register_username': 'e2e-student',
                'register_first_name': 'Grace',
                'register_last_name': 'Hopper',
                'register_email': 'grace@example.com',
                'register_cpf': '123.456.789-01',
                'register_birth_date': '2001-04-05',
                'register_phone': '(31) 97777-0000',
                'register_password': self.password,
                'register_password_confirm': self.password,
            },
        )

        self.assertEqual(register_response.status_code, 302)
        self.assertEqual(register_response.url, reverse('agora:index'))

        student = get_user_model().objects.get(username='e2e-student')
        self.assertEqual(student.profile.role, UserProfile.Role.STUDENT)
        self.assertEqual(int(self.client.session['_auth_user_id']), student.id)

        dashboard_response = self.client.get(register_response.url)

        self.assertEqual(dashboard_response.status_code, 200)
        self.assertContains(dashboard_response, 'Painel principal')

        courses_response = self.client.get(reverse('agora:courses_hub'))

        self.assertEqual(courses_response.status_code, 200)
        self.assertContains(courses_response, self.course.code)
        self.assertContains(courses_response, 'Solicitar Matrícula')

        request_response = self.client.post(
            reverse('agora:request_enrollment', args=[self.course.id]),
        )

        self.assertEqual(request_response.status_code, 302)
        self.assertEqual(request_response.url, reverse('agora:courses_hub'))

        enrollment = Enrollment.objects.get(student=student, course=self.course)
        self.assertEqual(enrollment.status, Enrollment.Status.PENDING)

        pending_response = self.client.get(reverse('agora:courses_hub'))

        self.assertEqual(pending_response.status_code, 200)
        self.assertContains(pending_response, 'Aguardando aprovação')
        self.assertNotContains(pending_response, 'Solicitar Matrícula')

        logout_response = self.client.post(reverse('agora:logout'))

        self.assertEqual(logout_response.status_code, 302)
        self.assertEqual(logout_response.url, reverse('agora:index'))
        self.assertNotIn('_auth_user_id', self.client.session)

        protected_response = self.client.get(reverse('agora:index'))

        self.assertEqual(protected_response.status_code, 302)
        self.assertTrue(protected_response.url.startswith(reverse('agora:login')))
