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


class AuthViewIntegrationTests(AgoraTestDataMixin, TestCase):
    def setUp(self):
        self.teacher = self.create_user('auth-teacher', UserProfile.Role.TEACHER)
        self.other_teacher = self.create_user('auth-other-teacher', UserProfile.Role.TEACHER)
        self.student = self.create_user('auth-student', UserProfile.Role.STUDENT)
        self.course = self.create_course(code='AUTH101', title='Auth Course', is_published=True)

    def valid_register_data(self, **overrides):
        data = {
            'action': 'register',
            'register_username': 'new-student',
            'register_first_name': 'New',
            'register_last_name': 'Student',
            'register_email': 'new-student@example.com',
            'register_cpf': '111.222.333-44',
            'register_birth_date': '2001-04-05',
            'register_phone': '(31) 97777-0000',
            'register_password': 'abc12345',
            'register_password_confirm': 'abc12345',
        }
        data.update(overrides)
        return data

    def test_authenticated_user_is_redirected_from_login_page(self):
        self.client.force_login(self.student)

        response = self.client.get(reverse('agora:login'))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('agora:index'))

    def test_login_accepts_academic_id_as_identifier(self):
        response = self.client.post(
            reverse('agora:login'),
            data={
                'action': 'login',
                'username': self.student.profile.academic_id,
                'password': self.password,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(self.client.session['_auth_user_id']), self.student.id)

    def test_login_rejects_bad_credentials_and_preserves_identifier(self):
        response = self.client.post(
            reverse('agora:login'),
            data={
                'action': 'login',
                'username': self.student.username,
                'password': 'wrong-password',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['error_message'], 'Usuário ou senha inválidos.')
        self.assertEqual(response.context['initial_username'], self.student.username)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_login_rejects_unknown_academic_id(self):
        response = self.client.post(
            reverse('agora:login'),
            data={
                'action': 'login',
                'username': '269999999',
                'password': self.password,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['error_message'], 'Usuário ou senha inválidos.')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_register_creates_student_profile_and_logs_user_in(self):
        response = self.client.post(
            reverse('agora:login'),
            data=self.valid_register_data(
                register_username='registered-student',
                register_first_name='Reg',
                register_email='registered@example.com',
                register_cpf='987.654.321-00',
                register_birth_date='2000-02-03',
                register_phone='(31) 90000-0000',
            ),
        )

        self.assertEqual(response.status_code, 302)
        user = get_user_model().objects.get(username='registered-student')
        self.assertEqual(user.profile.role, UserProfile.Role.STUDENT)
        self.assertEqual(user.profile.cpf, '98765432100')
        self.assertTrue(user.profile.academic_id)
        self.assertEqual(int(self.client.session['_auth_user_id']), user.id)
    def test_register_rejects_duplicate_cpf(self):
        self.student.profile.cpf = '98765432100'
        self.student.profile.save(update_fields=['cpf'])

        response = self.client.post(
            reverse('agora:login'),
            data=self.valid_register_data(
                register_username='duplicate-cpf',
                register_first_name='Dup',
                register_last_name='Cpf',
                register_email='dup@example.com',
                register_cpf='987.654.321-00',
                register_birth_date='2000-02-03',
                register_phone='(31) 90000-0000',
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['error_message'], 'Esse CPF já está em uso.')
        self.assertFalse(get_user_model().objects.filter(username='duplicate-cpf').exists())

    def test_register_validation_errors_keep_user_on_register_form(self):
        cases = [
            ({'register_username': ''}, 'Preencha usuário e senha para criar a conta.'),
            ({'register_password': ''}, 'Preencha usuário e senha para criar a conta.'),
            ({'register_first_name': ''}, 'Preencha nome e sobrenome.'),
            ({'register_last_name': ''}, 'Preencha nome e sobrenome.'),
            ({'register_email': ''}, 'Preencha o email.'),
            ({'register_cpf': ''}, 'Preencha o CPF.'),
            ({'register_cpf': '123'}, 'Informe um CPF válido.'),
            ({'register_birth_date': ''}, 'Preencha a data de nascimento.'),
            ({'register_phone': ''}, 'Preencha o telefone.'),
            ({'register_password_confirm': 'different'}, 'As senhas informadas não coincidem.'),
            ({'register_username': self.student.username}, 'Esse nome de usuário já está em uso.'),
            ({'register_birth_date': '05/04/2001'}, 'Informe uma data de nascimento válida.'),
        ]

        for index, (overrides, expected_error) in enumerate(cases, start=1):
            with self.subTest(expected_error=expected_error):
                data = self.valid_register_data(
                    register_username=f'invalid-student-{index}',
                    register_cpf=f'111222333{index:02d}'[:11],
                )
                data.update(overrides)
                response = self.client.post(
                    reverse('agora:login'),
                    data=data,
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context['active_form'], 'register')
                self.assertEqual(response.context['error_message'], expected_error)

        self.assertFalse(get_user_model().objects.filter(username__startswith='invalid-student-').exists())

    def test_logout_only_ends_session_on_post(self):
        self.client.force_login(self.student)

        get_response = self.client.get(reverse('agora:logout'))

        self.assertEqual(get_response.status_code, 302)
        self.assertEqual(int(self.client.session['_auth_user_id']), self.student.id)

        post_response = self.client.post(reverse('agora:logout'))

        self.assertEqual(post_response.status_code, 302)
        self.assertNotIn('_auth_user_id', self.client.session)
