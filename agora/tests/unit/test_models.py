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


class ModelValidationUnitTests(AgoraTestDataMixin, TestCase):
    def setUp(self):
        self.teacher = self.create_user('model-teacher', UserProfile.Role.TEACHER)
        self.student = self.create_user('model-student', UserProfile.Role.STUDENT)
        self.other_student = self.create_user('model-student-2', UserProfile.Role.STUDENT)
        self.course = self.create_course()
        self.module = Module.objects.create(course=self.course, title='Module 1', order=1)
        self.other_course = self.create_course(code='TST102', title='Other Course')
        self.other_module = Module.objects.create(course=self.other_course, title='Other Module', order=1)

    def test_user_profile_is_created_with_student_academic_id_by_signal(self):
        user_model = get_user_model()
        user = user_model.objects.create_user(username='auto-profile', password=self.password)

        self.assertTrue(hasattr(user, 'profile'))
        self.assertEqual(user.profile.role, UserProfile.Role.STUDENT)
        self.assertTrue(user.profile.academic_id.startswith(str(timezone.now().year)[-2:]))
        self.assertEqual(len(user.profile.academic_id), 9)

    def test_generate_academic_id_uses_next_valid_sequence_for_year(self):
        year_prefix = timezone.now().strftime('%y')
        self.student.profile.academic_id = f'{year_prefix}0000010'
        self.student.profile.save(update_fields=['academic_id'])
        self.other_student.profile.academic_id = f'{year_prefix}ABC'
        self.other_student.profile.save(update_fields=['academic_id'])

        self.assertEqual(generate_academic_id(), f'{year_prefix}0000011')

    def test_course_clean_rejects_student_as_teacher(self):
        course = Course(
            code='BAD101',
            title='Invalid Teacher',
            description='Invalid.',
            teacher=self.student,
        )

        with self.assertRaises(ValidationError) as context:
            course.full_clean()

        self.assertIn('teacher', context.exception.message_dict)

    def test_enrollment_clean_rejects_teacher_as_student(self):
        enrollment = Enrollment(student=self.teacher, course=self.course)

        with self.assertRaises(ValidationError) as context:
            enrollment.full_clean()

        self.assertIn('student', context.exception.message_dict)

    def test_course_item_clean_rejects_student_creator_and_foreign_module(self):
        item = AssignmentItem(
            course=self.course,
            module=self.other_module,
            title='Invalid item',
            description='Invalid module and creator.',
            created_by=self.student,
            due_date=timezone.now(),
            max_score=Decimal('10.00'),
        )

        with self.assertRaises(ValidationError) as context:
            item.full_clean()

        self.assertIn('created_by', context.exception.message_dict)
        self.assertIn('module', context.exception.message_dict)

    def test_course_item_polymorphism_resolves_detail_object_from_base_query(self):
        resource = ResourceItem.objects.create(
            course=self.course,
            module=self.module,
            title='Slides',
            description='Material.',
            attachment_url='https://example.com/slides',
            created_by=self.teacher,
        )
        assignment = AssignmentItem.objects.create(
            course=self.course,
            module=self.module,
            title='Lista',
            description='Tarefa.',
            due_date=timezone.now(),
            max_score=Decimal('10.00'),
            created_by=self.teacher,
        )
        quiz = QuizItem.objects.create(
            course=self.course,
            module=self.module,
            title='Quiz',
            description='Quiz.',
            due_date=timezone.now(),
            max_score=Decimal('5.00'),
            created_by=self.teacher,
        )
        forum = ForumItem.objects.create(
            course=self.course,
            module=self.module,
            title='Forum',
            description='Discussao.',
            created_by=self.teacher,
        )

        base_items = {item.id: item for item in CourseItem.objects.filter(id__in=[resource.id, assignment.id, quiz.id, forum.id])}

        self.assertEqual(base_items[resource.id].kind, 'resource')
        self.assertIsInstance(base_items[resource.id].detail_object, ResourceItem)
        self.assertEqual(base_items[assignment.id].kind, 'assignment')
        self.assertIsInstance(base_items[assignment.id].detail_object, AssignmentItem)
        self.assertEqual(base_items[quiz.id].kind, 'quiz')
        self.assertIsInstance(base_items[quiz.id].detail_object, QuizItem)
        self.assertEqual(base_items[forum.id].kind, 'forum')
        self.assertIsInstance(base_items[forum.id].detail_object, ForumItem)

    def test_resource_clean_requires_url_or_file(self):
        resource = ResourceItem(
            course=self.course,
            module=self.module,
            title='Empty resource',
            description='No attachment.',
            created_by=self.teacher,
        )

        with self.assertRaises(ValidationError):
            resource.full_clean()

    def test_submission_clean_validates_roles_score_and_content(self):
        assignment = AssignmentItem.objects.create(
            course=self.course,
            module=self.module,
            title='Lista',
            description='Tarefa.',
            due_date=timezone.now(),
            max_score=Decimal('5.00'),
            created_by=self.teacher,
        )
        submission = Submission(
            assignment=assignment,
            student=self.teacher,
            graded_by=self.student,
            score=Decimal('6.00'),
            content='',
        )

        with self.assertRaises(ValidationError) as context:
            submission.full_clean()

        self.assertIn('student', context.exception.message_dict)
        self.assertIn('graded_by', context.exception.message_dict)
        self.assertIn('score', context.exception.message_dict)
        self.assertIn('content', context.exception.message_dict)

    def test_forum_message_clean_requires_parent_from_same_forum(self):
        forum_a = ForumItem.objects.create(
            course=self.course,
            module=self.module,
            title='Forum A',
            description='A.',
            created_by=self.teacher,
        )
        forum_b = ForumItem.objects.create(
            course=self.course,
            module=self.module,
            title='Forum B',
            description='B.',
            created_by=self.teacher,
        )
        parent = ForumMessage.objects.create(forum=forum_a, author=self.teacher, content='Mensagem raiz.')
        reply = ForumMessage(forum=forum_b, author=self.student, parent=parent, content='Resposta fora do forum.')

        with self.assertRaises(ValidationError) as context:
            reply.full_clean()

        self.assertIn('parent', context.exception.message_dict)

    def test_answer_clean_requires_question_and_option_to_match_quiz(self):
        first = self.create_quiz_with_questions(title='Quiz 1')
        second = self.create_quiz_with_questions(title='Quiz 2')
        answer = Answer(
            quiz=first['quiz'],
            question=second['single'],
            selected_option=first['single_correct'],
            student=self.student,
        )

        with self.assertRaises(ValidationError) as context:
            answer.full_clean()

        self.assertIn('question', context.exception.message_dict)
        self.assertIn('selected_option', context.exception.message_dict)

    def test_submission_unique_constraint_blocks_duplicate_student_assignment(self):
        assignment = AssignmentItem.objects.create(
            course=self.course,
            module=self.module,
            title='Lista unica',
            description='Tarefa.',
            due_date=timezone.now(),
            max_score=Decimal('10.00'),
            created_by=self.teacher,
        )
        Submission.objects.create(assignment=assignment, student=self.student, status=Submission.Status.SUBMITTED, content='A')

        with self.assertRaises(IntegrityError), transaction.atomic():
            Submission.objects.create(
                assignment=assignment,
                student=self.student,
                status=Submission.Status.SUBMITTED,
                content='B',
            )
