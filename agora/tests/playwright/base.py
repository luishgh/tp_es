import os
from contextlib import contextmanager
from urllib.parse import urlparse

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.conf import settings
from django.test import Client

from playwright.sync_api import sync_playwright

from agora.tests.helpers import AgoraTestDataMixin


class PlaywrightTestCase(AgoraTestDataMixin, StaticLiveServerTestCase):
    browser = None
    playwright = None

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        if cls.browser is not None:
            cls.browser.close()
            cls.browser = None
        if cls.playwright is not None:
            cls.playwright.stop()
            cls.playwright = None
        super().tearDownClass()

    def create_page(self, user=None):
        context = self.browser.new_context(base_url=self.live_server_url)
        page = context.new_page()
        if user is not None:
            self._authenticate_context(context, user)
        return context, page

    def _authenticate_context(self, context, user):
        client = Client()
        client.force_login(user)
        parsed = urlparse(self.live_server_url)
        cookie_url = f'{parsed.scheme}://{parsed.hostname}:{parsed.port}'

        cookies = []
        session_cookie = client.cookies.get(settings.SESSION_COOKIE_NAME)
        if session_cookie is not None:
            cookies.append(
                {
                    'name': settings.SESSION_COOKIE_NAME,
                    'value': session_cookie.value,
                    'url': cookie_url,
                }
            )

        csrf_cookie = client.cookies.get(settings.CSRF_COOKIE_NAME)
        if csrf_cookie is not None:
            cookies.append(
                {
                    'name': settings.CSRF_COOKIE_NAME,
                    'value': csrf_cookie.value,
                    'url': cookie_url,
                }
            )

        if cookies:
            context.add_cookies(cookies)

    @contextmanager
    def browser_page(self, user=None):
        context, page = self.create_page(user=user)
        try:
            yield page
        finally:
            context.close()
