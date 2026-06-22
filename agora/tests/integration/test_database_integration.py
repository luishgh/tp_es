from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from agora.models import AssignmentItem, Course, Enrollment, Module, Submission, UserProfile


class CourseDatabaseIntegrationTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.teacher = user_model.objects.create_user(
            username='database-teacher',
            password='test-pass-123',
            first_name='Ada',
            last_name='Lovelace',
        )
        self.teacher.profile.role = UserProfile.Role.TEACHER
        self.teacher.profile.save(update_fields=['role'])

        self.student = user_model.objects.create_user(
            username='database-student',
            password='test-pass-123',
            first_name='Grace',
            last_name='Hopper',
        )
        self.student.profile.role = UserProfile.Role.STUDENT
        self.student.profile.save(update_fields=['role'])

        self.course = Course.objects.create(
            code='DB101',
            title='Database Integration',
            description='Course used to validate database integration.',
            syllabus='Database persistence and constraints.',
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
            title='Database assignment',
            description='Assignment used to validate submission persistence.',
            due_date=timezone.now() + timedelta(days=7),
            max_score=Decimal('10.00'),
            is_published=True,
            created_by=self.teacher,
        )

    def test_submission_is_persisted_and_database_prevents_duplicate_for_same_student(self):
        submission = Submission.objects.create(
            assignment=self.assignment,
            student=self.student,
            status=Submission.Status.SUBMITTED,
            content='First database-backed submission.',
            submitted_at=timezone.now(),
        )

        persisted_submission = Submission.objects.select_related(
            'assignment__course',
            'student__profile',
        ).get(pk=submission.pk)

        self.assertEqual(persisted_submission.assignment.course, self.course)
        self.assertEqual(persisted_submission.student.profile.role, UserProfile.Role.STUDENT)
        self.assertTrue(
            Enrollment.objects.filter(
                student=self.student,
                course=self.course,
                status=Enrollment.Status.ACTIVE,
            ).exists()
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Submission.objects.create(
                    assignment=self.assignment,
                    student=self.student,
                    status=Submission.Status.SUBMITTED,
                    content='Duplicate submission for the same assignment.',
                )

        self.assertEqual(
            Submission.objects.filter(assignment=self.assignment, student=self.student).count(),
            1,
        )

    def test_database_prevents_duplicate_enrollment_for_same_student_and_course(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Enrollment.objects.create(
                    student=self.student,
                    course=self.course,
                    status=Enrollment.Status.PENDING,
                )

        self.assertEqual(
            Enrollment.objects.filter(student=self.student, course=self.course).count(),
            1,
        )
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.status, Enrollment.Status.ACTIVE)

    def test_deleting_course_cascades_related_enrollments_assignments_and_submissions(self):
        submission = Submission.objects.create(
            assignment=self.assignment,
            student=self.student,
            status=Submission.Status.SUBMITTED,
            content='Submission removed with its course.',
            submitted_at=timezone.now(),
        )
        course_id = self.course.id
        assignment_id = self.assignment.id
        enrollment_id = self.enrollment.id
        submission_id = submission.id

        self.course.delete()

        self.assertFalse(Course.objects.filter(pk=course_id).exists())
        self.assertFalse(Enrollment.objects.filter(pk=enrollment_id).exists())
        self.assertFalse(AssignmentItem.objects.filter(pk=assignment_id).exists())
        self.assertFalse(Submission.objects.filter(pk=submission_id).exists())

    def test_deleting_module_keeps_assignment_and_clears_module_reference(self):
        module = Module.objects.create(
            course=self.course,
            title='Database module',
            description='Module used to validate SET_NULL persistence.',
            order=1,
        )
        self.assignment.module = module
        self.assignment.save()

        module_id = module.id
        assignment_id = self.assignment.id

        module.delete()
        self.assignment.refresh_from_db()

        self.assertFalse(Module.objects.filter(pk=module_id).exists())
        self.assertTrue(AssignmentItem.objects.filter(pk=assignment_id).exists())
        self.assertIsNone(self.assignment.module_id)
