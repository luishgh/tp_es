from django.urls import reverse

from agora.models import Enrollment, Module, ResourceItem, UserProfile
from agora.tests.playwright.base import PlaywrightTestCase


class TeacherContentBrowserFlowTests(PlaywrightTestCase):
    def setUp(self):
        self.teacher = self.create_user('browser-teacher', UserProfile.Role.TEACHER)
        self.student = self.create_user('browser-student', UserProfile.Role.STUDENT)

    def test_teacher_creates_course_module_and_published_material(self):
        with self.browser_page(user=self.teacher) as page:
            page.goto(self.live_server_url + reverse('agora:courses_hub'))
            page.get_by_label('Código do curso').fill('BROWSE202')
            page.get_by_label('Título').fill('Conteúdo no navegador')
            page.get_by_label('Descrição').fill('Curso criado via Playwright.')
            page.get_by_label('Ementa').fill('Estrutura, materiais e publicação.')
            page.get_by_label('Carga horária').fill('60')
            page.get_by_label('Disponível para matrículas').check()
            page.get_by_role('button', name='Criar curso').click()

            page.wait_for_url(self.live_server_url + reverse('agora:courses_hub') + '**')
            page.get_by_role('link').filter(has_text='BROWSE202').wait_for()

            course = self.teacher.courses_taught.get(code='BROWSE202')

            page.goto(self.live_server_url + reverse('agora:course_detail', args=[course.id]))
            page.get_by_role('link', name='Novo Módulo').click()

            page.wait_for_url(self.live_server_url + reverse('agora:module_create', args=[course.id]) + '**')
            page.get_by_label('Título do Módulo').fill('Primeiro módulo')
            page.get_by_label('Descrição').fill('Introdução do curso.')
            page.get_by_label('Ordem de exibição').fill('1')
            page.get_by_role('button', name='Criar Módulo').click()

            page.wait_for_url(self.live_server_url + reverse('agora:course_detail', args=[course.id]) + '**')
            page.get_by_role('heading', name='1. Primeiro módulo').wait_for()

            module = Module.objects.get(course=course, order=1)
            page.get_by_role('link', name='Novo Conteúdo').click()
            page.wait_for_url(self.live_server_url + reverse('agora:course_item_create', args=[course.id]) + '**')
            page.get_by_role('link', name='Material').click()
            page.get_by_label('Módulo').select_option(value=str(module.id))
            page.get_by_label('Título do material').fill('Slides publicados')
            page.get_by_label('Descrição').fill('Material publicado pelo professor.')
            page.get_by_label('Link do material').fill('https://example.com/slides-publicados.pdf')
            page.get_by_label('Publicar agora').check()
            page.get_by_role('button', name='Criar Material').click()

            page.wait_for_url(self.live_server_url + reverse('agora:course_detail', args=[course.id]) + '**')
            page.get_by_role('link').filter(has_text='Slides publicados').wait_for()

        course = self.teacher.courses_taught.get(code='BROWSE202')
        self.assertTrue(course.is_published)
        self.assertTrue(ResourceItem.objects.filter(course=course, title='Slides publicados').exists())

        Enrollment.objects.create(student=self.student, course=course, status=Enrollment.Status.ACTIVE)

        with self.browser_page(user=self.student) as page:
            page.goto(self.live_server_url + reverse('agora:course_detail', args=[course.id]))
            page.get_by_role('link').filter(has_text='Slides publicados').wait_for()
            page.get_by_text('Material publicado pelo professor.').wait_for()
