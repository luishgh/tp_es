from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from agora.models import Course, Enrollment, Module, ResourceItem, UserProfile


class TeacherContentStudentVisibilityE2ETests(TestCase):
    password = 'test-pass-123'

    def setUp(self):
        user_model = get_user_model()
        self.teacher = user_model.objects.create_user(
            username='content-teacher',
            password=self.password,
            first_name='Ada',
            last_name='Lovelace',
            email='content-teacher@example.com',
        )
        self.teacher.profile.role = UserProfile.Role.TEACHER
        self.teacher.profile.academic_id = ''
        self.teacher.profile.save(update_fields=['role', 'academic_id'])

        self.student = user_model.objects.create_user(
            username='content-student',
            password=self.password,
            first_name='Grace',
            last_name='Hopper',
            email='content-student@example.com',
        )
        self.student.profile.role = UserProfile.Role.STUDENT
        self.student.profile.ensure_academic_id(self.student.date_joined)
        self.student.profile.save(update_fields=['role', 'academic_id'])

    def test_teacher_creates_published_content_visible_to_enrolled_student(self):
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

        create_course_response = self.client.post(
            reverse('agora:courses_hub'),
            data={
                'action': 'create_course',
                'code': 'E2E202',
                'title': 'Teacher Published Content',
                'description': 'Course created through the teacher E2E flow.',
                'syllabus': 'Modules and published materials.',
                'workload_hours': '60',
                'is_published': 'on',
            },
        )

        self.assertEqual(create_course_response.status_code, 302)
        self.assertEqual(create_course_response.url, reverse('agora:courses_hub'))

        course = Course.objects.get(code='E2E202')
        self.assertEqual(course.teacher, self.teacher)
        self.assertTrue(course.is_published)

        course_detail_response = self.client.get(reverse('agora:course_detail', args=[course.id]))

        self.assertEqual(course_detail_response.status_code, 200)
        self.assertContains(course_detail_response, course.title)

        create_module_response = self.client.post(
            reverse('agora:module_create', args=[course.id]),
            data={
                'title': 'Primeiro módulo',
                'description': 'Conteúdo inicial do curso.',
                'order': '1',
            },
        )

        self.assertEqual(create_module_response.status_code, 302)
        self.assertEqual(create_module_response.url, reverse('agora:course_detail', args=[course.id]))

        module = Module.objects.get(course=course, order=1)

        create_material_response = self.client.post(
            reverse('agora:course_item_create', args=[course.id]),
            data={
                'activity_kind': 'resource',
                'module': str(module.id),
                'title': 'Slides publicados',
                'description': 'Material publicado pelo professor.',
                'attachment_url': 'https://example.com/slides-publicados.pdf',
                'is_published': 'on',
            },
        )

        self.assertEqual(create_material_response.status_code, 302)
        self.assertEqual(create_material_response.url, reverse('agora:course_detail', args=[course.id]))

        material = ResourceItem.objects.get(course=course, title='Slides publicados')
        self.assertEqual(material.module, module)
        self.assertTrue(material.is_published)

        teacher_course_page_response = self.client.get(reverse('agora:course_detail', args=[course.id]))

        self.assertEqual(teacher_course_page_response.status_code, 200)
        self.assertContains(teacher_course_page_response, 'Slides publicados')
        self.assertContains(teacher_course_page_response, 'Material publicado pelo professor.')

        teacher_logout_response = self.client.post(reverse('agora:logout'))

        self.assertEqual(teacher_logout_response.status_code, 302)
        self.assertNotIn('_auth_user_id', self.client.session)

        Enrollment.objects.create(
            student=self.student,
            course=course,
            status=Enrollment.Status.ACTIVE,
        )

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

        student_course_page_response = self.client.get(reverse('agora:course_detail', args=[course.id]))

        self.assertEqual(student_course_page_response.status_code, 200)
        self.assertContains(student_course_page_response, 'Slides publicados')
        self.assertContains(student_course_page_response, 'Material publicado pelo professor.')
