from django.urls import reverse

from agora.models import Enrollment, UserProfile
from agora.tests.playwright.base import PlaywrightTestCase


class EnrollmentBrowserFlowTests(PlaywrightTestCase):
    def setUp(self):
        self.teacher = self.create_user('browser-teacher', UserProfile.Role.TEACHER)
        self.student = self.create_user('browser-student', UserProfile.Role.STUDENT)
        self.course = self.create_course(
            teacher=self.teacher,
            code='BROWSE101',
            title='Browser Enrollment',
            is_published=True,
        )

    def test_student_requests_enrollment_and_sees_pending_state(self):
        with self.browser_page(user=self.student) as page:
            page.goto(self.live_server_url + reverse('agora:courses_hub'))
            page.get_by_text(self.course.code).wait_for()
            page.get_by_role('button', name='Solicitar Matrícula').click()

            page.wait_for_url(self.live_server_url + reverse('agora:courses_hub') + '**')
            page.get_by_text('Aguardando aprovação').wait_for()

        enrollment = Enrollment.objects.get(student=self.student, course=self.course)
        self.assertEqual(enrollment.status, Enrollment.Status.PENDING)
