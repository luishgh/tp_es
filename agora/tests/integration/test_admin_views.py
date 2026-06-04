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


class AdminViewsIntegrationTests(AgoraTestDataMixin, TestCase):
    def setUp(self):
        self.teacher = self.create_user('auth-teacher', UserProfile.Role.TEACHER)
        self.other_teacher = self.create_user('auth-other-teacher', UserProfile.Role.TEACHER)
        self.student = self.create_user('auth-student', UserProfile.Role.STUDENT)
        self.course = self.create_course(code='AUTH101', title='Auth Course', is_published=True)

    def test_superuser_create_user_view_requires_superuser_and_creates_user(self):
        superuser = get_user_model().objects.create_superuser(
            username='root',
            password=self.password,
            email='root@example.com',
        )
        self.client.force_login(superuser)

        response = self.client.post(
            reverse('agora:create_user'),
            data={
                'username': 'managed-student',
                'first_name': 'Managed',
                'last_name': 'Student',
                'email': 'managed@example.com',
                'password': 'abc12345',
                'password_confirm': 'abc12345',
                'role': UserProfile.Role.STUDENT,
                'cpf': '11122233344',
                'birth_date': '1999-01-01',
                'phone': '31911112222',
            },
        )

        self.assertEqual(response.status_code, 200)
        created = get_user_model().objects.get(username='managed-student')
        self.assertEqual(created.profile.role, UserProfile.Role.STUDENT)
        self.assertTrue(created.profile.academic_id)
