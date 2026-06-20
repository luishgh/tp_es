from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from agora.forms import (
    AssignmentCreateForm,
    AssignmentSubmissionForm,
    CourseCreateForm,
    ForumMessageForm,
    ModuleCreateForm,
    QuizCreateForm,
    ResourceCreateForm,
    SubmissionReviewForm,
    SuperuserCreateUserForm,
)
from agora.models import (
    Answer,
    AssignmentItem,
    Course,
    CourseItem,
    Enrollment,
    ForumItem,
    ForumMessage,
    Module,
    QuizItem,
    QuizOption,
    QuizQuestion,
    ResourceItem,
    Submission,
    UserProfile,
    generate_academic_id,
)
from agora.tests.helpers import AgoraTestDataMixin


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

    def test_course_detail_blocks_student_without_active_enrollment(self):
        self.client.force_login(self.inactive_student)

        response = self.client.get(reverse('agora:course_detail', args=[self.course.id]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('agora:courses_hub'))

    def test_course_detail_groups_items_and_counts_submissions_by_viewer(self):
        module = Module.objects.create(course=self.course, title='Module A', description='First module.', order=1)
        assignment = AssignmentItem.objects.create(
            course=self.course,
            module=module,
            title='Atividade com módulo',
            description='Entrega principal.',
            due_date=timezone.now() + timedelta(days=3),
            max_score=Decimal('10.00'),
            is_published=True,
            created_by=self.teacher,
        )
        ResourceItem.objects.create(
            course=self.course,
            title='Material sem módulo',
            description='Leitura independente.',
            attachment_url='https://example.com/material',
            is_published=True,
            created_by=self.teacher,
        )
        draft_assignment = AssignmentItem.objects.create(
            course=self.course,
            module=module,
            title='Rascunho reservado',
            description='Ainda não visível.',
            due_date=timezone.now() + timedelta(days=5),
            max_score=Decimal('5.00'),
            is_published=False,
            created_by=self.teacher,
        )
        Submission.objects.create(
            assignment=assignment,
            student=self.student,
            status=Submission.Status.SUBMITTED,
            content='Entrega ativa.',
        )
        Submission.objects.create(
            assignment=assignment,
            student=self.inactive_student,
            status=Submission.Status.SUBMITTED,
            content='Entrega não ativa.',
        )

        self.client.force_login(self.teacher)
        teacher_response = self.client.get(reverse('agora:course_detail', args=[self.course.id]))

        self.assertEqual(teacher_response.status_code, 200)
        module_data = teacher_response.context['modules_page'].object_list[0]
        teacher_activities = list(module_data['activities_page'].object_list)
        assignment_card = next(activity for activity in teacher_activities if activity['title'] == assignment.title)
        self.assertEqual(assignment_card['submission_count'], 2)
        self.assertIn(draft_assignment.title, {activity['title'] for activity in teacher_activities})

        no_module_response = self.client.get(f"{reverse('agora:course_detail', args=[self.course.id])}?module_page=2")
        no_module_data = no_module_response.context['modules_page'].object_list[0]
        self.assertEqual(no_module_data['title'], 'Itens sem módulo')
        self.assertEqual(no_module_data['activities_page'].object_list[0]['title'], 'Material sem módulo')

        self.client.force_login(self.student)
        student_response = self.client.get(reverse('agora:course_detail', args=[self.course.id]))

        self.assertEqual(student_response.status_code, 200)
        student_module_data = student_response.context['modules_page'].object_list[0]
        student_activities = list(student_module_data['activities_page'].object_list)
        student_assignment_card = next(activity for activity in student_activities if activity['title'] == assignment.title)
        self.assertEqual(student_assignment_card['submission_count'], 1)
        self.assertNotIn(draft_assignment.title, {activity['title'] for activity in student_activities})
class CoursePerformanceViewTests(TestCase):
    def setUp(self):
        user_model = get_user_model()

        self.teacher = user_model.objects.create_user(
            username='teacher-performance',
            password='test-pass-123',
            first_name='Ada',
            last_name='Lovelace',
        )
        self.teacher.profile.role = UserProfile.Role.TEACHER
        self.teacher.profile.save(update_fields=['role'])

        self.other_teacher = user_model.objects.create_user(
            username='other-teacher',
            password='test-pass-123',
            first_name='Barbara',
            last_name='Liskov',
        )
        self.other_teacher.profile.role = UserProfile.Role.TEACHER
        self.other_teacher.profile.save(update_fields=['role'])

        self.student = user_model.objects.create_user(
            username='student-performance',
            password='test-pass-123',
            first_name='Grace',
            last_name='Hopper',
        )
        self.student.profile.role = UserProfile.Role.STUDENT
        self.student.profile.academic_id = '260000001'
        self.student.profile.save(update_fields=['role', 'academic_id'])

        self.course = Course.objects.create(
            code='DCC300',
            title='Course Performance',
            description='Course used to validate teacher performance reports.',
            syllabus='Performance syllabus',
            workload_hours=60,
            teacher=self.teacher,
            is_published=True,
        )
        self.enrollment = Enrollment.objects.create(
            student=self.student,
            course=self.course,
            status=Enrollment.Status.ACTIVE,
        )

        self.assignment = AssignmentItem.objects.create(
            course=self.course,
            title='Lista 1',
            description='Entrega 1',
            due_date=timezone.now() + timedelta(days=3),
            max_score=10,
            created_by=self.teacher,
            is_published=True,
        )
        Submission.objects.create(
            assignment=self.assignment,
            student=self.student,
            status=Submission.Status.REVIEWED,
            content='Entrega pronta',
            score='8.5',
            feedback='Bom trabalho',
            submitted_at=timezone.now(),
            graded_at=timezone.now(),
            graded_by=self.teacher,
        )

    def test_teacher_can_view_course_performance(self):
        self.client.force_login(self.teacher)

        response = self.client.get(reverse('agora:course_performance', args=[self.course.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Desempenho dos alunos')
        self.assertContains(response, 'Grace Hopper')
        self.assertContains(response, 'Lista 1')
        self.assertContains(response, 'Bom trabalho')
        student_card = response.context['student_cards_page'].object_list[0]
        self.assertEqual(float(student_card['grade_form'].initial['final_grade']), 8.5)

    def test_other_teacher_cannot_view_course_performance(self):
        self.client.force_login(self.other_teacher)

        response = self.client.get(reverse('agora:course_performance', args=[self.course.id]))

        self.assertEqual(response.status_code, 302)

    def test_teacher_can_update_final_grade(self):
        self.client.force_login(self.teacher)

        response = self.client.post(
            reverse('agora:course_performance', args=[self.course.id]),
            data={
                'action': 'update_final_grade',
                'enrollment_id': str(self.enrollment.id),
                'student_page': '1',
                f'enrollment-{self.enrollment.id}-final_grade': '9.25',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.enrollment.refresh_from_db()
        self.assertEqual(float(self.enrollment.final_grade), 9.25)

    def test_teacher_performance_report_includes_quiz_scores_and_suggested_grade(self):
        quiz = QuizItem.objects.create(
            course=self.course,
            title='Quiz de revisão',
            description='Quiz usado no boletim.',
            due_date=timezone.now() + timedelta(days=1),
            max_score=Decimal('4.00'),
            allow_resubmissions=True,
            is_published=True,
            created_by=self.teacher,
        )
        question = QuizQuestion.objects.create(
            quiz=quiz,
            statement='Qual opção está correta?',
            order=1,
            weight=Decimal('4.00'),
        )
        correct = QuizOption.objects.create(question=question, text='Correta', is_correct=True, order=1)
        QuizOption.objects.create(question=question, text='Incorreta', is_correct=False, order=2)
        Answer.objects.create(
            quiz=quiz,
            question=question,
            selected_option=correct,
            student=self.student,
        )

        self.client.force_login(self.teacher)

        response = self.client.get(reverse('agora:course_performance', args=[self.course.id]))

        self.assertEqual(response.status_code, 200)
        student_card = response.context['student_cards_page'].object_list[0]
        quiz_report = next(item for item in student_card['items'] if item['kind'] == 'Quiz')
        self.assertEqual(quiz_report['title'], 'Quiz de revisão')
        self.assertEqual(quiz_report['status'], 'Respondido')
        self.assertEqual(quiz_report['score'], 4.0)
        self.assertEqual(student_card['delivered_count'], 2)
        self.assertEqual(student_card['graded_count'], 2)
        self.assertEqual(student_card['average_score'], 6.25)
        self.assertEqual(student_card['suggested_final_grade'], Decimal('12.50'))
class CourseEnrollmentIntegrationTests(AgoraTestDataMixin, TestCase):
    def setUp(self):
        self.teacher = self.create_user('auth-teacher', UserProfile.Role.TEACHER)
        self.other_teacher = self.create_user('auth-other-teacher', UserProfile.Role.TEACHER)
        self.student = self.create_user('auth-student', UserProfile.Role.STUDENT)
        self.course = self.create_course(code='AUTH101', title='Auth Course', is_published=True)

    def test_student_course_hub_shows_status_badges_for_existing_enrollments(self):
        active_course = self.create_course(code='ACTIVE', title='Active Course', is_published=True)
        pending_course = self.create_course(code='PEND', title='Pending Course', is_published=True)
        completed_course = self.create_course(code='DONE', title='Completed Course', is_published=True)
        cancelled_course = self.create_course(code='CANC', title='Cancelled Course', is_published=True)
        Enrollment.objects.create(student=self.student, course=self.course, status=Enrollment.Status.ACTIVE)
        Enrollment.objects.create(student=self.student, course=active_course, status=Enrollment.Status.ACTIVE)
        Enrollment.objects.create(student=self.student, course=pending_course, status=Enrollment.Status.PENDING)
        Enrollment.objects.create(student=self.student, course=completed_course, status=Enrollment.Status.COMPLETED)
        Enrollment.objects.create(student=self.student, course=cancelled_course, status=Enrollment.Status.CANCELLED)

        self.client.force_login(self.student)
        response = self.client.get(reverse('agora:courses_hub'))

        self.assertEqual(response.status_code, 200)
        cards = list(response.context['available_courses_page'].object_list)
        titles = {card['title']: card for card in cards}
        self.assertNotIn('Active Course', titles)
        self.assertEqual(titles['Pending Course']['status_badge'], 'Aguardando aprovação')
        self.assertEqual(titles['Completed Course']['status_badge'], 'Concluído')
        self.assertEqual(titles['Cancelled Course']['status_badge'], 'Solicitação recusada')

    def test_teacher_hub_lists_course_counts_pending_requests_and_creates_course(self):
        pending_student = self.create_user('pending-student', UserProfile.Role.STUDENT)
        Enrollment.objects.create(student=self.student, course=self.course, status=Enrollment.Status.ACTIVE)
        Enrollment.objects.create(student=pending_student, course=self.course, status=Enrollment.Status.PENDING)

        self.client.force_login(self.teacher)
        response = self.client.get(reverse('agora:courses_hub'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['taught_courses_count'], 1)
        self.assertEqual(response.context['pending_requests_count'], 1)
        course_card = response.context['taught_courses_page'].object_list[0]
        self.assertEqual(course_card['code'], 'AUTH101')
        self.assertEqual(course_card['active_students'], 1)
        self.assertEqual(response.context['pending_requests_page'].object_list[0].student, pending_student)

        create_response = self.client.post(
            reverse('agora:courses_hub'),
            data={
                'action': 'create_course',
                'code': 'new101',
                'title': 'Novo Curso',
                'description': 'Curso criado pelo hub.',
                'syllabus': 'Conteúdo.',
                'workload_hours': '45',
                'is_published': 'on',
            },
        )

        self.assertEqual(create_response.status_code, 302)
        created_course = Course.objects.get(code='NEW101')
        self.assertEqual(created_course.teacher, self.teacher)
        self.assertTrue(created_course.is_published)

    def test_student_can_request_enrollment_and_reopen_cancelled_request(self):
        Enrollment.objects.create(
            student=self.student,
            course=self.course,
            status=Enrollment.Status.CANCELLED,
            final_grade=Decimal('4.00'),
        )
        self.client.force_login(self.student)

        response = self.client.post(reverse('agora:request_enrollment', args=[self.course.id]))

        self.assertEqual(response.status_code, 302)
        enrollment = Enrollment.objects.get(student=self.student, course=self.course)
        self.assertEqual(enrollment.status, Enrollment.Status.PENDING)
        self.assertIsNone(enrollment.final_grade)

    def test_request_enrollment_requires_student_post_and_handles_existing_statuses(self):
        self.client.force_login(self.teacher)
        teacher_response = self.client.post(reverse('agora:request_enrollment', args=[self.course.id]))
        self.assertEqual(teacher_response.status_code, 302)
        self.assertFalse(Enrollment.objects.filter(student=self.teacher, course=self.course).exists())

        self.client.force_login(self.student)
        get_response = self.client.get(reverse('agora:request_enrollment', args=[self.course.id]))
        self.assertEqual(get_response.status_code, 302)
        self.assertFalse(Enrollment.objects.filter(student=self.student, course=self.course).exists())

        new_course = self.create_course(code='NEWREQ', title='New Request', is_published=True)
        new_response = self.client.post(reverse('agora:request_enrollment', args=[new_course.id]))
        self.assertEqual(new_response.status_code, 302)
        self.assertEqual(
            Enrollment.objects.get(student=self.student, course=new_course).status,
            Enrollment.Status.PENDING,
        )

        existing_statuses = [
            (Enrollment.Status.ACTIVE, Decimal('8.00')),
            (Enrollment.Status.PENDING, None),
            (Enrollment.Status.COMPLETED, Decimal('9.50')),
        ]
        for index, (status, final_grade) in enumerate(existing_statuses, start=1):
            with self.subTest(status=status):
                course = self.create_course(code=f'KEEP{index}', title=f'Keep {status}', is_published=True)
                Enrollment.objects.create(
                    student=self.student,
                    course=course,
                    status=status,
                    final_grade=final_grade,
                )

                response = self.client.post(reverse('agora:request_enrollment', args=[course.id]))

                self.assertEqual(response.status_code, 302)
                enrollment = Enrollment.objects.get(student=self.student, course=course)
                self.assertEqual(enrollment.status, status)
                self.assertEqual(enrollment.final_grade, final_grade)

    def test_teacher_accepts_and_rejects_only_own_pending_enrollments(self):
        own_request = Enrollment.objects.create(student=self.student, course=self.course, status=Enrollment.Status.PENDING)
        other_course = self.create_course(
            teacher=self.other_teacher,
            code='AUTH102',
            title='Other Teacher Course',
            is_published=True,
        )
        other_request = Enrollment.objects.create(student=self.student, course=other_course, status=Enrollment.Status.PENDING)
        self.client.force_login(self.teacher)

        accepted = self.client.post(reverse('agora:enrollment_decision', args=[own_request.id, 'accept']))
        blocked = self.client.post(reverse('agora:enrollment_decision', args=[other_request.id, 'reject']))

        self.assertEqual(accepted.status_code, 302)
        self.assertEqual(blocked.status_code, 404)
        own_request.refresh_from_db()
        other_request.refresh_from_db()
        self.assertEqual(own_request.status, Enrollment.Status.ACTIVE)
        self.assertEqual(other_request.status, Enrollment.Status.PENDING)

    def test_enrollment_decision_handles_non_post_non_teacher_processed_and_reject(self):
        pending = Enrollment.objects.create(student=self.student, course=self.course, status=Enrollment.Status.PENDING)

        self.client.force_login(self.teacher)
        get_response = self.client.get(reverse('agora:enrollment_decision', args=[pending.id, 'accept']))
        pending.refresh_from_db()
        self.assertEqual(get_response.status_code, 302)
        self.assertEqual(pending.status, Enrollment.Status.PENDING)

        self.client.force_login(self.student)
        student_response = self.client.post(reverse('agora:enrollment_decision', args=[pending.id, 'accept']))
        pending.refresh_from_db()
        self.assertEqual(student_response.status_code, 302)
        self.assertEqual(pending.status, Enrollment.Status.PENDING)

        pending.status = Enrollment.Status.ACTIVE
        pending.save(update_fields=['status'])
        self.client.force_login(self.teacher)
        processed_response = self.client.post(reverse('agora:enrollment_decision', args=[pending.id, 'accept']))
        pending.refresh_from_db()
        self.assertEqual(processed_response.status_code, 302)
        self.assertEqual(pending.status, Enrollment.Status.ACTIVE)

        reject_request = Enrollment.objects.create(
            student=self.create_user('reject-student', UserProfile.Role.STUDENT),
            course=self.course,
            status=Enrollment.Status.PENDING,
        )
        reject_response = self.client.post(reverse('agora:enrollment_decision', args=[reject_request.id, 'reject']))
        reject_request.refresh_from_db()
        self.assertEqual(reject_response.status_code, 302)
        self.assertEqual(reject_request.status, Enrollment.Status.CANCELLED)

    def test_publish_course_requires_owner_and_post(self):
        draft = self.create_course(code='DRAFT', title='Draft', is_published=False)
        self.client.force_login(self.other_teacher)
        forbidden = self.client.post(reverse('agora:publish_course', args=[draft.id]))
        draft.refresh_from_db()

        self.assertEqual(forbidden.status_code, 302)
        self.assertFalse(draft.is_published)

        self.client.force_login(self.teacher)
        get_response = self.client.get(reverse('agora:publish_course', args=[draft.id]))
        draft.refresh_from_db()
        post_response = self.client.post(reverse('agora:publish_course', args=[draft.id]))
        draft.refresh_from_db()

        self.assertEqual(get_response.status_code, 302)
        self.assertEqual(post_response.status_code, 302)
        self.assertTrue(draft.is_published)

    def test_publish_course_is_idempotent_for_already_published_course(self):
        self.client.force_login(self.teacher)

        response = self.client.post(reverse('agora:publish_course', args=[self.course.id]))

        self.assertEqual(response.status_code, 302)
        self.course.refresh_from_db()
        self.assertTrue(self.course.is_published)
