from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import UserProfile


class AuthenticationFlowTests(TestCase):
    def test_register_creates_student_with_generated_academic_id(self):
        response = self.client.post(
            reverse('agora:login'),
            {
                'action': 'register',
                'register_username': 'alice',
                'register_first_name': 'Alice',
                'register_last_name': 'Silva',
                'register_email': 'alice@example.com',
                'register_cpf': '123.456.789-10',
                'register_birth_date': '2000-05-10',
                'register_social_name': 'Ali',
                'register_phone': '(65) 99999-0000',
                'register_password': 'senha-forte-123',
                'register_password_confirm': 'senha-forte-123',
            },
        )

        self.assertRedirects(response, reverse('agora:index'))

        user = get_user_model().objects.get(username='alice')
        self.assertEqual(user.first_name, 'Alice')
        self.assertEqual(user.last_name, 'Silva')
        self.assertEqual(user.profile.role, UserProfile.Role.STUDENT)
        self.assertEqual(user.profile.cpf, '123.456.789-10')
        self.assertEqual(str(user.profile.birth_date), '2000-05-10')
        self.assertEqual(user.profile.social_name, 'Ali')
        self.assertEqual(user.profile.phone, '(65) 99999-0000')
        self.assertRegex(user.profile.academic_id, r'^\d{9}$')
        self.assertTrue(user.profile.academic_id.startswith('26'))

    def test_login_accepts_academic_id(self):
        user = get_user_model().objects.create_user(
            username='bob',
            email='bob@example.com',
            password='senha-forte-123',
        )

        response = self.client.post(
            reverse('agora:login'),
            {
                'action': 'login',
                'username': user.profile.academic_id,
                'password': 'senha-forte-123',
            },
        )

        self.assertRedirects(response, reverse('agora:index'))
