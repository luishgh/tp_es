from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .models import AssignmentItem, Course, Enrollment, Module, ResourceItem, Submission, UserProfile


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
        self.client.force_login(self.student)

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

    def test_teacher_can_create_assignment_with_module_from_same_course(self):
        self.client.force_login(self.teacher)

        response = self.client.post(
            reverse('agora:course_item_create', args=[self.course.id]),
            data={
                'activity_kind': 'assignment',
                'module': str(self.module.id),
                'title': 'Lista 1',
                'description': 'Exercícios da semana.',
                'statement_url': 'https://example.com/enunciado',
                'due_date': '2026-04-30T23:59',
                'max_score': '10',
                'is_published': 'on',
            },
        )

        self.assertEqual(response.status_code, 302)
        activity = AssignmentItem.objects.get(title='Lista 1')
        self.assertEqual(activity.course_id, self.course.id)
        self.assertEqual(activity.module_id, self.module.id)

    def test_teacher_cannot_create_activity_with_module_from_other_course(self):
        self.client.force_login(self.teacher)

        response = self.client.post(
            reverse('agora:course_item_create', args=[self.course.id]),
            data={
                'activity_kind': 'assignment',
                'module': str(self.other_module.id),
                'title': 'Lista X',
                'description': 'Teste.',
                'statement_url': 'https://example.com/enunciado',
                'due_date': '2026-04-30T23:59',
                'max_score': '10',
                'is_published': 'on',
            },
        )

        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertIn('module', form.errors)

    def test_teacher_can_create_material_without_due_date_and_max_score(self):
        self.client.force_login(self.teacher)

        response = self.client.post(
            reverse('agora:course_item_create', args=[self.course.id]),
            data={
                'activity_kind': 'resource',
                'module': str(self.module.id),
                'title': 'Slides 1',
                'description': 'Material de apoio.',
                'attachment_url': 'https://example.com/slides',
                'is_published': 'on',
            },
        )

        self.assertEqual(response.status_code, 302)
        activity = ResourceItem.objects.get(title='Slides 1')
        self.assertEqual(activity.attachment_url, 'https://example.com/slides')

    def test_teacher_can_create_material_with_uploaded_file(self):
        self.client.force_login(self.teacher)

        uploaded_file = SimpleUploadedFile(
            'slides.pdf',
            b'%PDF-1.4 fake pdf content',
            content_type='application/pdf',
        )

        response = self.client.post(
            reverse('agora:course_item_create', args=[self.course.id]),
            data={
                'activity_kind': 'resource',
                'module': str(self.module.id),
                'title': 'Arquivo 1',
                'description': 'Material com upload.',
                'attachment_file': uploaded_file,
                'is_published': 'on',
            },
        )

        self.assertEqual(response.status_code, 302)
        activity = ResourceItem.objects.get(title='Arquivo 1')
        self.assertTrue(bool(activity.attachment_file))
        self.assertEqual(activity.attachment_url, '')

    def test_assignment_requires_max_score(self):
        self.client.force_login(self.teacher)

        response = self.client.post(
            reverse('agora:course_item_create', args=[self.course.id]),
            data={
                'activity_kind': 'assignment',
                'module': str(self.module.id),
                'title': 'Lista sem nota',
                'description': 'Teste.',
                'statement_url': 'https://example.com/enunciado',
                'due_date': '2026-04-30T23:59',
                'is_published': 'on',
            },
        )

        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertIn('max_score', form.errors)


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

        self.assignment = AssignmentItem.objects.create(
            course=self.course,
            module=self.module,
            title='Trabalho 1',
            description='SQL exercises.',
            statement_url='https://example.com/spec',
            due_date='2026-04-30T23:59Z',
            max_score=10,
            is_published=True,
            created_by=self.teacher,
        )
        self.material = ResourceItem.objects.create(
            course=self.course,
            module=self.module,
            title='Leitura 1',
            description='Slides.',
            attachment_url='https://example.com/slides',
            is_published=True,
            created_by=self.teacher,
        )
        self.draft_assignment = AssignmentItem.objects.create(
            course=self.course,
            module=self.module,
            title='Rascunho',
            description='Draft.',
            due_date='2026-05-10T23:59Z',
            max_score=10,
            is_published=False,
            created_by=self.teacher,
        )

    def test_student_can_view_published_activity_detail(self):
        self.client.force_login(self.student)

        response = self.client.get(reverse('agora:course_item_detail', args=[self.material.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Leitura 1')
        self.assertContains(response, 'Abrir link')
        self.assertContains(response, 'Acesse o conteúdo')

    def test_student_cannot_view_unpublished_activity_detail(self):
        self.client.force_login(self.student)

        response = self.client.get(reverse('agora:course_item_detail', args=[self.draft_assignment.id]))

        self.assertEqual(response.status_code, 302)

    def test_non_enrolled_student_is_blocked(self):
        self.client.force_login(self.other_student)

        response = self.client.get(reverse('agora:course_item_detail', args=[self.assignment.id]))

        self.assertEqual(response.status_code, 302)

    def test_teacher_sees_submissions_for_assignment(self):
        Submission.objects.create(
            assignment=self.assignment,
            student=self.student,
            status=Submission.Status.SUBMITTED,
        )

        self.client.force_login(self.teacher)

        response = self.client.get(reverse('agora:course_item_detail', args=[self.assignment.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Entregas dos alunos')
        self.assertContains(response, 'Grace Hopper')

    def test_teacher_can_review_submission(self):
        submission = Submission.objects.create(
            assignment=self.assignment,
            student=self.student,
            status=Submission.Status.SUBMITTED,
            content='Minha entrega',
        )

        self.client.force_login(self.teacher)

        response = self.client.post(
            reverse('agora:submission_review', args=[submission.id]),
            data={
                'score': '8.5',
                'feedback': 'Boa resolução, mas faltou otimizar uma consulta.',
            },
        )

        self.assertEqual(response.status_code, 302)
        submission.refresh_from_db()
        self.assertEqual(submission.status, Submission.Status.REVIEWED)
        self.assertEqual(float(submission.score), 8.5)
        self.assertEqual(submission.feedback, 'Boa resolução, mas faltou otimizar uma consulta.')
        self.assertEqual(submission.graded_by, self.teacher)
        self.assertIsNotNone(submission.graded_at)

    def test_teacher_can_update_existing_review(self):
        submission = Submission.objects.create(
            assignment=self.assignment,
            student=self.student,
            status=Submission.Status.REVIEWED,
            score='7.0',
            feedback='Primeira versão da correção.',
            graded_by=self.teacher,
            content='Minha entrega',
        )

        self.client.force_login(self.teacher)

        response = self.client.post(
            reverse('agora:submission_review', args=[submission.id]),
            data={
                'score': '9.0',
                'feedback': 'Correção atualizada após revisão.',
            },
        )

        self.assertEqual(response.status_code, 302)
        submission.refresh_from_db()
        self.assertEqual(submission.status, Submission.Status.REVIEWED)
        self.assertEqual(float(submission.score), 9.0)
        self.assertEqual(submission.feedback, 'Correção atualizada após revisão.')

    def test_teacher_can_publish_activity(self):
        self.assignment.is_published = False
        self.assignment.save(update_fields=['is_published'])

        self.client.force_login(self.teacher)

        response = self.client.post(reverse('agora:publish_course_item', args=[self.assignment.id]))

        self.assertEqual(response.status_code, 302)
        self.assignment.refresh_from_db()
        self.assertTrue(self.assignment.is_published)

    def test_publish_activity_is_idempotent(self):
        self.client.force_login(self.teacher)

        first = self.client.post(reverse('agora:publish_course_item', args=[self.assignment.id]))
        second = self.client.post(reverse('agora:publish_course_item', args=[self.assignment.id]))

        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.assignment.refresh_from_db()
        self.assertTrue(self.assignment.is_published)
