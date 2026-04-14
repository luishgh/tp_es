from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Activity, Course, Enrollment, Module, Submission, UserProfile


class CourseDetailViewTests(TestCase):
    def setUp(self):
        user_model = get_user_model()

        self.viewer = user_model.objects.create_user(
            username='viewer',
            password='test-pass-123',
            first_name='View',
            last_name='Only',
        )

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

        self.inactive_student = user_model.objects.create_user(
            username='student02',
            password='test-pass-123',
            first_name='Alan',
            last_name='Turing',
        )
        self.inactive_student.profile.role = UserProfile.Role.STUDENT
        self.inactive_student.profile.save(update_fields=['role'])

        self.course = Course.objects.create(
            code='DCC001',
            title='Algorithms Studio',
            description='A focused course page used to validate the standalone detail layout.',
            syllabus='Core concepts and practice.',
            workload_hours=60,
            teacher=self.teacher,
            is_published=True,
        )

        Enrollment.objects.create(
            student=self.student,
            course=self.course,
            status=Enrollment.Status.ACTIVE,
        )
        Enrollment.objects.create(
            student=self.inactive_student,
            course=self.course,
            status=Enrollment.Status.PENDING,
        )

    def test_course_detail_renders_professor_and_active_students_from_database(self):
        self.client.force_login(self.viewer)

        response = self.client.get(reverse('agora:course_detail', args=[self.course.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Algorithms Studio')
        self.assertContains(response, 'Ada Lovelace')
        self.assertContains(response, 'Grace Hopper')
        self.assertContains(response, '20260001')
        self.assertNotContains(response, 'Alan Turing')
        self.assertContains(response, 'Nenhuma atividade disponível ainda.')


class ActivityCreateViewTests(TestCase):
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

        self.other_teacher = user_model.objects.create_user(
            username='teacher02',
            password='test-pass-123',
            first_name='Barbara',
            last_name='Liskov',
            email='barbara@example.com',
        )
        self.other_teacher.profile.role = UserProfile.Role.TEACHER
        self.other_teacher.profile.save(update_fields=['role'])

        self.course = Course.objects.create(
            code='DCC101',
            title='Programming 1',
            description='Intro course.',
            syllabus='Basics.',
            workload_hours=60,
            teacher=self.teacher,
            is_published=True,
        )
        self.module = Module.objects.create(
            course=self.course,
            title='Week 1',
            description='Getting started.',
            order=1,
        )

        self.other_course = Course.objects.create(
            code='DCC102',
            title='Programming 2',
            description='Follow-up course.',
            syllabus='More topics.',
            workload_hours=60,
            teacher=self.other_teacher,
            is_published=True,
        )
        self.other_module = Module.objects.create(
            course=self.other_course,
            title='Other Module',
            description='Other.',
            order=1,
        )

    def test_teacher_can_create_activity_with_module_from_same_course(self):
        self.client.force_login(self.teacher)

        response = self.client.post(
            reverse('agora:activity_create', args=[self.course.id]),
            data={
                'module': str(self.module.id),
                'title': 'Lista 1',
                'description': 'Exercícios da semana.',
                'activity_type': Activity.Type.ASSIGNMENT,
                'attachment_url': '',
                'due_date': '2026-04-30T23:59',
                'max_score': '10',
                'is_published': 'on',
            },
        )

        self.assertEqual(response.status_code, 302)
        activity = Activity.objects.get(title='Lista 1')
        self.assertEqual(activity.course_id, self.course.id)
        self.assertEqual(activity.module_id, self.module.id)

    def test_teacher_cannot_create_activity_with_module_from_other_course(self):
        self.client.force_login(self.teacher)

        response = self.client.post(
            reverse('agora:activity_create', args=[self.course.id]),
            data={
                'module': str(self.other_module.id),
                'title': 'Lista X',
                'description': 'Teste.',
                'activity_type': Activity.Type.ASSIGNMENT,
                'attachment_url': '',
                'due_date': '2026-04-30T23:59',
                'max_score': '10',
                'is_published': 'on',
            },
        )

        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertIn('module', form.errors)


class ResourceDetailViewTests(TestCase):
    def setUp(self):
        user_model = get_user_model()

        self.teacher = user_model.objects.create_user(
            username='teacher01',
            password='test-pass-123',
            first_name='Ada',
            last_name='Lovelace',
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
        self.student.profile.save(update_fields=['role'])

        self.other_student = user_model.objects.create_user(
            username='student02',
            password='test-pass-123',
            first_name='Alan',
            last_name='Turing',
        )
        self.other_student.profile.role = UserProfile.Role.STUDENT
        self.other_student.profile.save(update_fields=['role'])

        self.course = Course.objects.create(
            code='DCC201',
            title='Databases',
            description='Intro.',
            syllabus='Core.',
            workload_hours=60,
            teacher=self.teacher,
            is_published=True,
        )
        self.module = Module.objects.create(course=self.course, title='Week 1', order=1)

        Enrollment.objects.create(student=self.student, course=self.course, status=Enrollment.Status.ACTIVE)

        self.assignment = Activity.objects.create(
            course=self.course,
            module=self.module,
            title='Trabalho 1',
            description='SQL exercises.',
            activity_type=Activity.Type.ASSIGNMENT,
            attachment_url='https://example.com/spec',
            due_date=None,
            max_score=10,
            is_published=True,
            created_by=self.teacher,
        )
        self.material = Activity.objects.create(
            course=self.course,
            module=self.module,
            title='Leitura 1',
            description='Slides.',
            activity_type=Activity.Type.RESOURCE,
            attachment_url='https://example.com/slides',
            due_date=None,
            max_score=0,
            is_published=True,
            created_by=self.teacher,
        )
        self.draft_assignment = Activity.objects.create(
            course=self.course,
            module=self.module,
            title='Rascunho',
            description='Draft.',
            activity_type=Activity.Type.ASSIGNMENT,
            attachment_url='',
            due_date=None,
            max_score=10,
            is_published=False,
            created_by=self.teacher,
        )

    def test_student_can_view_published_activity_detail(self):
        self.client.force_login(self.student)

        response = self.client.get(reverse('agora:resource_detail', args=[self.material.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Leitura 1')
        self.assertContains(response, 'Abrir link')
        self.assertContains(response, 'Situação de Envio')

    def test_student_cannot_view_unpublished_activity_detail(self):
        self.client.force_login(self.student)

        response = self.client.get(reverse('agora:resource_detail', args=[self.draft_assignment.id]))

        self.assertEqual(response.status_code, 302)

    def test_non_enrolled_student_is_blocked(self):
        self.client.force_login(self.other_student)

        response = self.client.get(reverse('agora:resource_detail', args=[self.assignment.id]))

        self.assertEqual(response.status_code, 302)

    def test_teacher_sees_submissions_for_assignment(self):
        Submission.objects.create(
            activity=self.assignment,
            student=self.student,
            status=Submission.Status.SUBMITTED,
        )

        self.client.force_login(self.teacher)

        response = self.client.get(reverse('agora:resource_detail', args=[self.assignment.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Entregas dos Alunos')
        self.assertContains(response, 'Grace Hopper')
