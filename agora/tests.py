from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

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

    def test_teacher_can_create_assignment_with_module_from_same_course(self):
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

    def test_teacher_can_create_material_without_due_date_and_max_score(self):
        self.client.force_login(self.teacher)

        response = self.client.post(
            reverse('agora:activity_create', args=[self.course.id]),
            data={
                'module': str(self.module.id),
                'title': 'Slides 1',
                'description': 'Material de apoio.',
                'activity_type': Activity.Type.RESOURCE,
                'attachment_url': 'https://example.com/slides',
                'is_published': 'on',
            },
        )

        self.assertEqual(response.status_code, 302)
        activity = Activity.objects.get(title='Slides 1')
        self.assertEqual(activity.activity_type, Activity.Type.RESOURCE)
        self.assertIsNone(activity.due_date)
        self.assertIsNone(activity.max_score)

    def test_assignment_requires_max_score(self):
        self.client.force_login(self.teacher)

        response = self.client.post(
            reverse('agora:activity_create', args=[self.course.id]),
            data={
                'module': str(self.module.id),
                'title': 'Lista sem nota',
                'description': 'Teste.',
                'activity_type': Activity.Type.ASSIGNMENT,
                'attachment_url': '',
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
            max_score=None,
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

    def test_teacher_can_publish_activity(self):
        self.assignment.is_published = False
        self.assignment.save(update_fields=['is_published'])

        self.client.force_login(self.teacher)

        response = self.client.post(reverse('agora:publish_activity', args=[self.assignment.id]))

        self.assertEqual(response.status_code, 302)
        self.assignment.refresh_from_db()
        self.assertTrue(self.assignment.is_published)

    def test_publish_activity_is_idempotent(self):
        self.client.force_login(self.teacher)

        first = self.client.post(reverse('agora:publish_activity', args=[self.assignment.id]))
        second = self.client.post(reverse('agora:publish_activity', args=[self.assignment.id]))

        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.assignment.refresh_from_db()
        self.assertTrue(self.assignment.is_published)


class CalendarViewTests(TestCase):
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

        self.student = user_model.objects.create_user(
            username='student01',
            password='test-pass-123',
            first_name='Grace',
            last_name='Hopper',
        )
        self.student.profile.role = UserProfile.Role.STUDENT
        self.student.profile.academic_id = '20260001'
        self.student.profile.save(update_fields=['role', 'academic_id'])

        self.course_a = Course.objects.create(
            code='MATH',
            title='Matemática',
            description='Curso de matemática.',
            syllabus='Cálculo.',
            workload_hours=60,
            teacher=self.teacher,
            is_published=True,
        )

        self.course_b = Course.objects.create(
            code='FIS',
            title='Física',
            description='Curso de física.',
            syllabus='Cinemática.',
            workload_hours=60,
            teacher=self.teacher,
            is_published=True,
        )

        Enrollment.objects.create(student=self.student, course=self.course_a, status=Enrollment.Status.ACTIVE)
        Enrollment.objects.create(student=self.student, course=self.course_b, status=Enrollment.Status.ACTIVE)

        due = timezone.now() + timedelta(hours=10)

        self.activity_alpha = Activity.objects.create(
            course=self.course_a,
            title='Alpha',
            description='Tarefa A.',
            activity_type=Activity.Type.ASSIGNMENT,
            attachment_url='',
            due_date=due,
            max_score=10,
            is_published=True,
            created_by=self.teacher,
        )
        self.activity_beta = Activity.objects.create(
            course=self.course_a,
            title='Beta',
            description='Tarefa B.',
            activity_type=Activity.Type.ASSIGNMENT,
            attachment_url='',
            due_date=due,
            max_score=10,
            is_published=True,
            created_by=self.teacher,
        )
        self.activity_gamma = Activity.objects.create(
            course=self.course_b,
            title='Gamma',
            description='Tarefa C.',
            activity_type=Activity.Type.ASSIGNMENT,
            attachment_url='',
            due_date=due,
            max_score=10,
            is_published=True,
            created_by=self.teacher,
        )
        self.activity_delta = Activity.objects.create(
            course=self.course_b,
            title='Delta',
            description='Tarefa D.',
            activity_type=Activity.Type.ASSIGNMENT,
            attachment_url='',
            due_date=due,
            max_score=10,
            is_published=True,
            created_by=self.teacher,
        )
        self.activity_sent = Activity.objects.create(
            course=self.course_b,
            title='Enviada',
            description='Tarefa enviada.',
            activity_type=Activity.Type.ASSIGNMENT,
            attachment_url='',
            due_date=due,
            max_score=10,
            is_published=True,
            created_by=self.teacher,
        )

        Submission.objects.create(
            activity=self.activity_sent,
            student=self.student,
            status=Submission.Status.SUBMITTED,
            content='Resposta',
        )

        self.grade_newest = Activity.objects.create(
            course=self.course_a,
            title='Atividade corrigida 1',
            description='Para nota',
            activity_type=Activity.Type.ASSIGNMENT,
            attachment_url='',
            due_date=due,
            max_score=10,
            is_published=True,
            created_by=self.teacher,
        )
        self.grade_older = Activity.objects.create(
            course=self.course_a,
            title='Atividade corrigida 2',
            description='Para nota 2',
            activity_type=Activity.Type.ASSIGNMENT,
            attachment_url='',
            due_date=due - timedelta(days=1),
            max_score=10,
            is_published=True,
            created_by=self.teacher,
        )
        self.grade_without_mark = Activity.objects.create(
            course=self.course_b,
            title='Corrigida sem data',
            description='Sem data',
            activity_type=Activity.Type.ASSIGNMENT,
            attachment_url='',
            due_date=due,
            max_score=10,
            is_published=True,
            created_by=self.teacher,
        )

        Submission.objects.create(
            activity=self.grade_newest,
            student=self.student,
            status=Submission.Status.REVIEWED,
            content='Resposta',
            score=9,
            feedback='Ótimo',
            graded_at=timezone.now() - timedelta(hours=1),
            graded_by=self.teacher,
        )
        Submission.objects.create(
            activity=self.grade_older,
            student=self.student,
            status=Submission.Status.REVIEWED,
            content='Resposta',
            score=8,
            feedback='Bom',
            graded_at=timezone.now() - timedelta(days=2),
            graded_by=self.teacher,
        )
        Submission.objects.create(
            activity=self.grade_without_mark,
            student=self.student,
            status=Submission.Status.REVIEWED,
            content='Resposta',
            score=7,
            feedback='Sem data',
        )

    def test_student_can_access_calendar(self):
        self.client.force_login(self.student)

        response = self.client.get(reverse('agora:calendar'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="calendar-prev-month"')
        self.assertContains(response, 'id="calendar-next-month"')
        self.assertContains(response, 'id="calendar-today-month"')

    def test_teacher_is_redirected_from_calendar(self):
        self.client.force_login(self.teacher)

        response = self.client.get(reverse('agora:calendar'))

        self.assertEqual(response.status_code, 302)

    def test_pending_agenda_is_top_three_sorted_by_date_and_course_code(self):
        self.client.force_login(self.student)

        response = self.client.get(reverse('agora:calendar'))
        agenda_items = response.context['agenda_items']

        self.assertEqual(len(agenda_items), 3)
        self.assertEqual(
            [item['title'] for item in agenda_items],
            ['Delta', 'Gamma', 'Alpha'],
        )
        self.assertNotIn('Enviada', [item['title'] for item in agenda_items])

    def test_grade_cards_are_ordered_by_most_recent_graded(self):
        self.client.force_login(self.student)

        response = self.client.get(reverse('agora:calendar'))
        grade_cards = response.context['grade_cards']

        self.assertEqual(len(grade_cards), 2)
        self.assertEqual(
            [grade['activity_title'] for grade in grade_cards],
            [self.grade_newest.title, self.grade_older.title],
        )

    def test_calendar_data_and_list_items_include_detail_links(self):
        self.client.force_login(self.student)

        response = self.client.get(reverse('agora:calendar'))
        agenda_items = response.context['agenda_items']
        grade_cards = response.context['grade_cards']

        for item in agenda_items:
            self.assertContains(response, reverse('agora:resource_detail', args=[item['id']]))

        for grade in grade_cards:
            self.assertContains(response, reverse('agora:resource_detail', args=[grade['id']]))

        calendar_items = response.context['calendar_items']
        self.assertTrue(all('detail_url' in item for item in calendar_items))
