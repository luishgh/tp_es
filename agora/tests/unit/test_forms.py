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


class FormUnitTests(AgoraTestDataMixin, TestCase):
    def setUp(self):
        self.teacher = self.create_user('form-teacher', UserProfile.Role.TEACHER)
        self.student = self.create_user('form-student', UserProfile.Role.STUDENT)
        self.course = self.create_course()
        self.module = Module.objects.create(course=self.course, title='Modulo 1', order=1)
        self.other_course = self.create_course(code='FRM102', title='Outro curso')
        self.other_module = Module.objects.create(course=self.other_course, title='Modulo externo', order=1)

    def test_course_create_form_normalizes_code_and_title(self):
        form = CourseCreateForm(
            data={
                'code': ' dcc999 ',
                'title': ' Novo curso ',
                'description': 'Descricao',
                'syllabus': '',
                'workload_hours': '40',
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['code'], 'DCC999')
        self.assertEqual(form.cleaned_data['title'], 'Novo curso')

    def test_module_create_form_rejects_duplicate_order_in_same_course(self):
        form = ModuleCreateForm(
            data={'title': 'Modulo duplicado', 'description': '', 'order': '1'},
            course=self.course,
        )

        self.assertFalse(form.is_valid())
        self.assertIn('__all__', form.errors)

    def test_resource_create_form_filters_modules_and_requires_source(self):
        form = ResourceCreateForm(
            data={
                'module': str(self.other_module.id),
                'title': 'Material',
                'description': 'Sem fonte.',
                'attachment_url': '',
            },
            course=self.course,
        )
        form.instance.course = self.course
        form.instance.created_by = self.teacher

        self.assertFalse(form.is_valid())
        self.assertIn('module', form.errors)
        self.assertIn('__all__', form.errors)
        self.assertNotIn(self.other_module, form.fields['module'].queryset)

    def test_assignment_create_form_accepts_date_time_fields_and_sets_due_date(self):
        form = AssignmentCreateForm(
            data={
                'module': str(self.module.id),
                'title': ' Lista 1 ',
                'description': 'Exercicios.',
                'statement_url': 'https://example.com/spec',
                'due_date_date': '2026-05-01',
                'due_date_time': '14:30',
                'max_score': '10',
                'is_published': 'on',
            },
            course=self.course,
        )
        form.instance.course = self.course
        form.instance.created_by = self.teacher

        self.assertTrue(form.is_valid(), form.errors)
        assignment = form.save()
        self.assertEqual(assignment.title, 'Lista 1')
        self.assertTrue(timezone.is_aware(assignment.due_date))
        self.assertEqual(assignment.due_date.hour, 14)
        self.assertEqual(assignment.due_date.minute, 30)

    def test_assignment_create_form_accepts_legacy_due_date_payload(self):
        form = AssignmentCreateForm(
            data={
                'module': str(self.module.id),
                'title': 'Lista antiga',
                'description': 'Compatibilidade.',
                'statement_url': 'https://example.com/spec',
                'due_date': '2026-05-01T23:59',
                'max_score': '7.5',
            },
            course=self.course,
        )
        form.instance.course = self.course
        form.instance.created_by = self.teacher

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['due_date'].hour, 23)
        self.assertEqual(form.cleaned_data['due_date'].minute, 59)

    def test_quiz_create_form_rejects_single_choice_without_exactly_one_correct_option(self):
        form = QuizCreateForm(
            data={
                'module': str(self.module.id),
                'title': 'Quiz invalido',
                'description': 'Sem correta.',
                'question_count': '1',
                'question_1_statement': 'Pergunta?',
                'question_1_type': QuizQuestion.QuestionType.SINGLE_CHOICE,
                'question_1_score': '2',
                'question_1_option_1': 'A',
                'question_1_option_2': 'B',
                'question_1_option_3': 'C',
                'question_1_option_4': 'D',
                'due_date_date': '2026-05-01',
                'due_date_time': '10:00',
            },
            course=self.course,
        )
        form.instance.course = self.course
        form.instance.created_by = self.teacher

        self.assertFalse(form.is_valid())
        self.assertIn('question_1_type', form.errors)

    def test_quiz_create_form_rejects_duplicate_options_and_bad_image_extension(self):
        bad_image = SimpleUploadedFile('question.gif', b'GIF89a', content_type='image/gif')
        form = QuizCreateForm(
            data={
                'module': str(self.module.id),
                'title': 'Quiz invalido',
                'description': 'Duplicado.',
                'question_count': '1',
                'question_1_statement': 'Pergunta?',
                'question_1_type': QuizQuestion.QuestionType.MULTIPLE_CHOICE,
                'question_1_score': '2',
                'question_1_option_1': 'A',
                'question_1_option_1_is_correct': 'on',
                'question_1_option_2': 'A',
                'question_1_option_3': 'C',
                'question_1_option_4': 'D',
                'due_date_date': '2026-05-01',
                'due_date_time': '10:00',
            },
            files={'question_1_image': bad_image},
            course=self.course,
        )
        form.instance.course = self.course
        form.instance.created_by = self.teacher

        self.assertFalse(form.is_valid())
        self.assertIn('question_1_option_2', form.errors)
        self.assertIn('question_1_image', form.errors)

    def test_quiz_create_form_saves_and_replaces_questions_atomically(self):
        data = {
            'module': str(self.module.id),
            'title': 'Quiz valido',
            'description': 'Formulario.',
            'question_count': '2',
            'question_1_statement': 'Pergunta 1?',
            'question_1_type': QuizQuestion.QuestionType.SINGLE_CHOICE,
            'question_1_score': '4',
            'question_1_option_1': 'A',
            'question_1_option_1_is_correct': 'on',
            'question_1_option_2': 'B',
            'question_1_option_3': 'C',
            'question_1_option_4': 'D',
            'question_2_statement': 'Pergunta 2?',
            'question_2_type': QuizQuestion.QuestionType.MULTIPLE_CHOICE,
            'question_2_score': '6',
            'question_2_option_1': 'A',
            'question_2_option_1_is_correct': 'on',
            'question_2_option_2': 'B',
            'question_2_option_3': 'C',
            'question_2_option_3_is_correct': 'on',
            'question_2_option_4': 'D',
            'due_date_date': '2026-05-01',
            'due_date_time': '10:00',
        }
        form = QuizCreateForm(data=data, course=self.course)
        form.instance.course = self.course
        form.instance.created_by = self.teacher

        self.assertTrue(form.is_valid(), form.errors)
        quiz = form.save()
        self.assertEqual(quiz.questions.count(), 2)
        self.assertEqual(quiz.max_score, Decimal('10.00'))

        edit_data = data.copy()
        edit_data.update(
            {
                'title': 'Quiz editado',
                'question_count': '1',
                'question_1_statement': 'Nova pergunta?',
                'question_1_score': '8',
            }
        )
        edit_form = QuizCreateForm(data=edit_data, course=self.course, instance=quiz)
        edit_form.instance.course = self.course
        edit_form.instance.created_by = self.teacher

        self.assertTrue(edit_form.is_valid(), edit_form.errors)
        quiz = edit_form.save()
        self.assertEqual(quiz.title, 'Quiz editado')
        self.assertEqual(quiz.questions.count(), 1)
        self.assertEqual(quiz.max_score, Decimal('8.00'))
        self.assertEqual(quiz.questions.first().statement, 'Nova pergunta?')

    def test_submission_review_form_rejects_score_above_assignment_max(self):
        assignment = AssignmentItem.objects.create(
            course=self.course,
            module=self.module,
            title='Lista',
            description='Tarefa.',
            due_date=timezone.now(),
            max_score=Decimal('5.00'),
            created_by=self.teacher,
        )
        submission = Submission.objects.create(
            assignment=assignment,
            student=self.student,
            status=Submission.Status.SUBMITTED,
            content='Entrega.',
        )
        form = SubmissionReviewForm(
            data={'score': '5.01', 'feedback': 'Acima do limite.'},
            instance=submission,
            assignment=assignment,
        )

        self.assertFalse(form.is_valid())
        self.assertIn('score', form.errors)

    def test_assignment_submission_form_requires_content_or_file_but_accepts_existing_file(self):
        assignment = AssignmentItem.objects.create(
            course=self.course,
            module=self.module,
            title='Lista',
            description='Tarefa.',
            due_date=timezone.now(),
            max_score=Decimal('5.00'),
            created_by=self.teacher,
        )
        empty_form = AssignmentSubmissionForm(data={'content': ''})

        self.assertFalse(empty_form.is_valid())
        self.assertIn('__all__', empty_form.errors)

        submission = Submission.objects.create(
            assignment=assignment,
            student=self.student,
            status=Submission.Status.SUBMITTED,
            content='Original.',
            attachment_file=SimpleUploadedFile('answer.txt', b'answer'),
        )
        existing_file_form = AssignmentSubmissionForm(data={'content': ''}, instance=submission)

        self.assertTrue(existing_file_form.is_valid(), existing_file_form.errors)

    def test_superuser_create_user_form_saves_teacher_and_normalizes_formatted_cpf(self):
        form = SuperuserCreateUserForm(
            data={
                'username': 'new-teacher',
                'first_name': 'Nova',
                'last_name': 'Professora',
                'email': 'nova@example.com',
                'password': 'abc12345',
                'password_confirm': 'abc12345',
                'role': UserProfile.Role.TEACHER,
                'cpf': '123.456.789-00',
                'birth_date': '1990-01-02',
                'phone': '(31) 99999-9999',
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertEqual(user.profile.role, UserProfile.Role.TEACHER)
        self.assertEqual(user.profile.cpf, '12345678900')
        self.assertEqual(user.profile.academic_id, '')
        self.assertEqual(user.profile.birth_date, date(1990, 1, 2))

    def test_superuser_create_user_form_rejects_duplicate_cpf_and_password_mismatch(self):
        self.student.profile.cpf = '12345678900'
        self.student.profile.save(update_fields=['cpf'])
        form = SuperuserCreateUserForm(
            data={
                'username': 'dup-cpf',
                'first_name': 'Dup',
                'last_name': 'Cpf',
                'email': 'dup@example.com',
                'password': 'abc12345',
                'password_confirm': 'different',
                'role': UserProfile.Role.STUDENT,
                'cpf': '12345678900',
                'birth_date': '1990-01-02',
                'phone': '31999999999',
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn('cpf', form.errors)
        self.assertIn('password_confirm', form.errors)

    def test_forum_message_form_strips_blank_content(self):
        blank = ForumMessageForm(data={'content': '   '})
        valid = ForumMessageForm(data={'content': '  Conteudo util  '})

        self.assertFalse(blank.is_valid())
        self.assertTrue(valid.is_valid(), valid.errors)
        self.assertEqual(valid.cleaned_data['content'], 'Conteudo util')
