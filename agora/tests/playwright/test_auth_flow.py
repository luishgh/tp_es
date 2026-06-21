from django.urls import reverse

from agora.models import UserProfile
from agora.tests.playwright.base import PlaywrightTestCase


class AuthBrowserFlowTests(PlaywrightTestCase):
    def setUp(self):
        self.student = self.create_user('browser-student', UserProfile.Role.STUDENT)

    def test_authenticated_user_sees_dashboard_and_can_logout_from_ui(self):
        with self.browser_page(user=self.student) as page:
            page.goto(self.live_server_url + reverse('agora:index'))

            page.get_by_text('Painel principal').wait_for()
            page.get_by_text(self.student.username).wait_for()
            page.get_by_role('button', name='Logout').click()

            page.wait_for_url(self.live_server_url + reverse('agora:index') + '**')
            self.assertTrue(page.url.endswith(reverse('agora:index')))
