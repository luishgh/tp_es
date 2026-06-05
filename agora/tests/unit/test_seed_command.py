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


class SeedCommandTests(TestCase):
    def test_seed_command_creates_idempotent_demo_dataset_and_reset_is_scoped(self):
        out = StringIO()

        call_command('seed', '--reset', '--seed', '7', '--password', 'demo123', stdout=out)
        first_counts = {
            'users': get_user_model().objects.filter(username__startswith='demo_').count(),
            'courses': Course.objects.filter(code__startswith='DEMO-').count(),
            'items': CourseItem.objects.filter(course__code__startswith='DEMO-').count(),
            'enrollments': Enrollment.objects.filter(course__code__startswith='DEMO-').count(),
        }
        call_command('seed', '--seed', '7', '--password', 'demo123', stdout=StringIO())
        second_counts = {
            'users': get_user_model().objects.filter(username__startswith='demo_').count(),
            'courses': Course.objects.filter(code__startswith='DEMO-').count(),
            'items': CourseItem.objects.filter(course__code__startswith='DEMO-').count(),
            'enrollments': Enrollment.objects.filter(course__code__startswith='DEMO-').count(),
        }

        self.assertEqual(first_counts, second_counts)
        self.assertEqual(first_counts['users'], 11)
        self.assertEqual(first_counts['courses'], 3)
        self.assertGreater(first_counts['items'], 0)
        self.assertGreater(first_counts['enrollments'], 0)
        self.assertIn('Resumo demo', out.getvalue())
