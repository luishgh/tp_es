from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Course, Enrollment, UserProfile


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
