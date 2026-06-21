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
            reverse('agora:course_item_create', args=[self.course.id]),
            data={
                'activity_kind': 'assignment',
                'module': str(self.module.id),
                'title': 'Lista 1',
                'description': 'Exercícios da semana.',
                'statement_url': 'https://example.com/enunciado',
                'due_date': '2026-04-30T23:59',
                'max_score': '10',
                'is_published': 'on',
            },
        )

        self.assertEqual(response.status_code, 302)
        activity = AssignmentItem.objects.get(title='Lista 1')
        self.assertEqual(activity.course_id, self.course.id)
        self.assertEqual(activity.module_id, self.module.id)

    def test_teacher_cannot_create_activity_with_module_from_other_course(self):
        self.client.force_login(self.teacher)

        response = self.client.post(
            reverse('agora:course_item_create', args=[self.course.id]),
            data={
                'activity_kind': 'assignment',
                'module': str(self.other_module.id),
                'title': 'Lista X',
                'description': 'Teste.',
                'statement_url': 'https://example.com/enunciado',
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
            reverse('agora:course_item_create', args=[self.course.id]),
            data={
                'activity_kind': 'resource',
                'module': str(self.module.id),
                'title': 'Slides 1',
                'description': 'Material de apoio.',
                'attachment_url': 'https://example.com/slides',
                'is_published': 'on',
            },
        )

        self.assertEqual(response.status_code, 302)
        activity = ResourceItem.objects.get(title='Slides 1')
        self.assertEqual(activity.attachment_url, 'https://example.com/slides')

    def test_teacher_can_create_material_with_uploaded_file(self):
        self.client.force_login(self.teacher)

        uploaded_file = SimpleUploadedFile(
            'slides.pdf',
            b'%PDF-1.4 fake pdf content',
            content_type='application/pdf',
        )

        response = self.client.post(
            reverse('agora:course_item_create', args=[self.course.id]),
            data={
                'activity_kind': 'resource',
                'module': str(self.module.id),
                'title': 'Arquivo 1',
                'description': 'Material com upload.',
                'attachment_file': uploaded_file,
                'is_published': 'on',
            },
        )

        self.assertEqual(response.status_code, 302)
        activity = ResourceItem.objects.get(title='Arquivo 1')
        self.assertTrue(bool(activity.attachment_file))
        self.assertEqual(activity.attachment_url, '')

    def test_assignment_requires_max_score(self):
        self.client.force_login(self.teacher)

        response = self.client.post(
            reverse('agora:course_item_create', args=[self.course.id]),
            data={
                'activity_kind': 'assignment',
                'module': str(self.module.id),
                'title': 'Lista sem nota',
                'description': 'Teste.',
                'statement_url': 'https://example.com/enunciado',
                'due_date': '2026-04-30T23:59',
                'is_published': 'on',
            },
        )

        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertIn('max_score', form.errors)

    def test_teacher_can_create_quiz_with_single_multiple_choice_question(self):
        self.client.force_login(self.teacher)

        question_image = SimpleUploadedFile(
            'question.png',
            b'\x89PNG\r\n\x1a\nfakepng',
            content_type='image/png',
        )

        response = self.client.post(
            reverse('agora:course_item_create', args=[self.course.id]),
            data={
                'activity_kind': 'quiz',
                'module': str(self.module.id),
                'title': 'Quiz 1',
                'description': 'Quiz de revisão.',
                'question_count': '2',
                'question_1_statement': 'Qual linguagem o Django usa principalmente?',
                'question_1_image': question_image,
                'question_1_type': 'single_choice',
                'question_1_score': '4',
                'question_1_option_1': 'Python',
                'question_1_option_1_is_correct': 'on',
                'question_1_option_2': 'Ruby',
                'question_1_option_3': 'PHP',
                'question_1_option_4': 'Go',
                'question_2_statement': 'Qual comando inicia o servidor de desenvolvimento?',
                'question_2_type': 'multiple_choice',
                'question_2_score': '6',
                'question_2_option_1': 'python manage.py migrate',
                'question_2_option_1_is_correct': 'on',
                'question_2_option_2': 'python manage.py runserver',
                'question_2_option_2_is_correct': 'on',
                'question_2_option_3': 'python manage.py test',
                'question_2_option_4': 'python manage.py shell',
                'due_date': '2026-04-30T23:59',
                'allow_resubmissions': 'on',
                'is_published': 'on',
            },
        )

        self.assertEqual(response.status_code, 302)
        quiz = QuizItem.objects.get(title='Quiz 1')
        self.assertEqual(float(quiz.max_score), 10.0)
        self.assertTrue(quiz.allow_resubmissions)
        questions = list(QuizQuestion.objects.filter(quiz=quiz).order_by('order'))
        self.assertEqual(len(questions), 2)
        self.assertEqual(questions[0].statement, 'Qual linguagem o Django usa principalmente?')
        self.assertEqual(questions[0].question_type, QuizQuestion.QuestionType.SINGLE_CHOICE)
        self.assertTrue(bool(questions[0].image))
        self.assertEqual(float(questions[0].weight), 4.0)
        self.assertEqual(questions[0].options.count(), 4)
        self.assertEqual(questions[0].options.get(is_correct=True).text, 'Python')
        self.assertEqual(questions[1].question_type, QuizQuestion.QuestionType.MULTIPLE_CHOICE)
        self.assertEqual(float(questions[1].weight), 6.0)
        self.assertEqual(
            set(questions[1].options.filter(is_correct=True).values_list('text', flat=True)),
            {'python manage.py migrate', 'python manage.py runserver'},
        )

    def test_teacher_can_disable_quiz_resubmissions(self):
        self.client.force_login(self.teacher)

        response = self.client.post(
            reverse('agora:course_item_create', args=[self.course.id]),
            data={
                'activity_kind': 'quiz',
                'module': str(self.module.id),
                'title': 'Quiz sem reenvio',
                'description': 'Teste.',
                'question_count': '1',
                'question_1_statement': 'Pergunta única?',
                'question_1_type': 'single_choice',
                'question_1_score': '5',
                'question_1_option_1': 'A',
                'question_1_option_1_is_correct': 'on',
                'question_1_option_2': 'B',
                'question_1_option_3': 'C',
                'question_1_option_4': 'D',
                'due_date': '2026-04-30T23:59',
                'is_published': 'on',
            },
        )

        self.assertEqual(response.status_code, 302)
        quiz = QuizItem.objects.get(title='Quiz sem reenvio')
        self.assertFalse(quiz.allow_resubmissions)

    def test_course_item_create_get_selects_requested_type_and_falls_back_to_resource(self):
        self.client.force_login(self.teacher)

        forum_response = self.client.get(f"{reverse('agora:course_item_create', args=[self.course.id])}?type=forum")
        fallback_response = self.client.get(f"{reverse('agora:course_item_create', args=[self.course.id])}?type=unknown")

        self.assertEqual(forum_response.status_code, 200)
        self.assertEqual(forum_response.context['selected_type'], 'forum')
        self.assertEqual(forum_response.context['form_title'], 'Criar Novo Fórum')
        self.assertEqual(forum_response.context['form'].instance.course, self.course)
        self.assertEqual(forum_response.context['form'].instance.created_by, self.teacher)
        self.assertEqual(fallback_response.context['selected_type'], 'resource')
        self.assertEqual(fallback_response.context['form_title'], 'Criar Novo Material')

    def test_other_teacher_cannot_open_course_item_create_form(self):
        self.client.force_login(self.other_teacher)

        response = self.client.get(reverse('agora:course_item_create', args=[self.course.id]))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(CourseItem.objects.filter(course=self.course, title='Material').exists())

    def test_teacher_can_create_forum_item(self):
        self.client.force_login(self.teacher)

        response = self.client.post(
            reverse('agora:course_item_create', args=[self.course.id]),
            data={
                'activity_kind': 'forum',
                'module': str(self.module.id),
                'title': 'Fórum 1',
                'description': 'Espaço de discussão.',
                'is_published': 'on',
            },
        )

        self.assertEqual(response.status_code, 302)
        forum = ForumItem.objects.get(title='Fórum 1')
        self.assertEqual(forum.course, self.course)
        self.assertEqual(forum.module, self.module)
        self.assertEqual(forum.created_by, self.teacher)
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

        self.other_teacher = user_model.objects.create_user(
            username='teacher02',
            password='test-pass-123',
            first_name='Barbara',
            last_name='Liskov',
        )
        self.other_teacher.profile.role = UserProfile.Role.TEACHER
        self.other_teacher.profile.save(update_fields=['role'])

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

        self.assignment = AssignmentItem.objects.create(
            course=self.course,
            module=self.module,
            title='Trabalho 1',
            description='SQL exercises.',
            statement_url='https://example.com/spec',
            due_date='2026-04-30T23:59Z',
            max_score=10,
            is_published=True,
            created_by=self.teacher,
        )
        self.material = ResourceItem.objects.create(
            course=self.course,
            module=self.module,
            title='Leitura 1',
            description='Slides.',
            attachment_url='https://example.com/slides',
            is_published=True,
            created_by=self.teacher,
        )
        self.draft_assignment = AssignmentItem.objects.create(
            course=self.course,
            module=self.module,
            title='Rascunho',
            description='Draft.',
            due_date='2026-05-10T23:59Z',
            max_score=10,
            is_published=False,
            created_by=self.teacher,
        )
        self.quiz = QuizItem.objects.create(
            course=self.course,
            module=self.module,
            title='Quiz rápido',
            description='Teste de revisão.',
            due_date='2026-04-29T23:59Z',
            max_score=10,
            allow_resubmissions=True,
            is_published=True,
            created_by=self.teacher,
        )
        self.quiz_question = QuizQuestion.objects.create(
            quiz=self.quiz,
            statement='Qual comando cria migrations no Django?',
            order=1,
            weight=4,
        )
        self.correct_quiz_option = QuizOption.objects.create(
            question=self.quiz_question,
            text='python manage.py makemigrations',
            is_correct=True,
            order=1,
        )
        self.quiz_option_2 = QuizOption.objects.create(
            question=self.quiz_question,
            text='python manage.py runserver',
            is_correct=False,
            order=2,
        )
        self.quiz_question_2 = QuizQuestion.objects.create(
            quiz=self.quiz,
            statement='Qual comando aplica migrations?',
            question_type=QuizQuestion.QuestionType.MULTIPLE_CHOICE,
            order=2,
            weight=6,
        )
        self.quiz_question_2_option_1 = QuizOption.objects.create(
            question=self.quiz_question_2,
            text='python manage.py migrate',
            is_correct=True,
            order=1,
        )
        self.quiz_question_2_option_2 = QuizOption.objects.create(
            question=self.quiz_question_2,
            text='python manage.py collectstatic',
            is_correct=False,
            order=2,
        )
        self.quiz_question_2_option_3 = QuizOption.objects.create(
            question=self.quiz_question_2,
            text='python manage.py runserver',
            is_correct=True,
            order=3,
        )

    def test_student_can_view_published_activity_detail(self):
        self.client.force_login(self.student)

        response = self.client.get(reverse('agora:course_item_detail', args=[self.material.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Leitura 1')
        self.assertContains(response, 'Abrir link')
        self.assertContains(response, 'Acesse o conteúdo')

    def test_resource_detail_lists_download_action_for_uploaded_file(self):
        file_material = ResourceItem.objects.create(
            course=self.course,
            module=self.module,
            title='Arquivo de apoio',
            description='Material enviado como arquivo.',
            attachment_file=SimpleUploadedFile('apoio.txt', b'conteudo do arquivo', content_type='text/plain'),
            is_published=True,
            created_by=self.teacher,
        )

        self.client.force_login(self.student)

        response = self.client.get(reverse('agora:course_item_detail', args=[file_material.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['material_actions'][0]['label'], 'Baixar arquivo')
        self.assertEqual(response.context['material_actions'][0]['tone'], 'primary')

    def test_student_cannot_view_unpublished_activity_detail(self):
        self.client.force_login(self.student)

        response = self.client.get(reverse('agora:course_item_detail', args=[self.draft_assignment.id]))

        self.assertEqual(response.status_code, 302)

    def test_non_enrolled_student_is_blocked(self):
        self.client.force_login(self.other_student)

        response = self.client.get(reverse('agora:course_item_detail', args=[self.assignment.id]))

        self.assertEqual(response.status_code, 302)

    def test_student_gets_existing_submission_form_and_status(self):
        submission = Submission.objects.create(
            assignment=self.assignment,
            student=self.student,
            status=Submission.Status.REVIEWED,
            content='Entrega revisada',
            score=Decimal('8.00'),
            feedback='Bom trabalho.',
            submitted_at=timezone.now(),
            graded_at=timezone.now(),
            graded_by=self.teacher,
        )

        self.client.force_login(self.student)

        response = self.client.get(reverse('agora:course_item_detail', args=[self.assignment.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['current_submission'], submission)
        self.assertEqual(response.context['assignment_form'].instance, submission)
        self.assertEqual(response.context['submission_status']['label'], submission.get_status_display())
        self.assertEqual(response.context['submission_status']['tone'], 'accent')

    def test_teacher_sees_submissions_for_assignment(self):
        Submission.objects.create(
            assignment=self.assignment,
            student=self.student,
            status=Submission.Status.SUBMITTED,
        )

        self.client.force_login(self.teacher)

        response = self.client.get(reverse('agora:course_item_detail', args=[self.assignment.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Entregas dos alunos')
        self.assertContains(response, 'Grace Hopper')

    def test_teacher_submission_list_exposes_status_tones(self):
        reviewed_student = get_user_model().objects.create_user(
            username='reviewed-student',
            password='test-pass-123',
            first_name='Reviewed',
            last_name='Student',
        )
        reviewed_student.profile.role = UserProfile.Role.STUDENT
        reviewed_student.profile.save(update_fields=['role'])
        draft_student = get_user_model().objects.create_user(
            username='draft-student',
            password='test-pass-123',
            first_name='Draft',
            last_name='Student',
        )
        draft_student.profile.role = UserProfile.Role.STUDENT
        draft_student.profile.save(update_fields=['role'])
        submitted = Submission.objects.create(
            assignment=self.assignment,
            student=self.student,
            status=Submission.Status.SUBMITTED,
            content='Entrega enviada',
        )
        late = Submission.objects.create(
            assignment=self.assignment,
            student=self.other_student,
            status=Submission.Status.LATE,
            content='Entrega atrasada',
        )
        reviewed = Submission.objects.create(
            assignment=self.assignment,
            student=reviewed_student,
            status=Submission.Status.REVIEWED,
            content='Entrega avaliada',
            score=Decimal('9.00'),
        )
        draft = Submission.objects.create(
            assignment=self.assignment,
            student=draft_student,
            status=Submission.Status.DRAFT,
            content='Rascunho salvo',
        )

        self.client.force_login(self.teacher)

        response = self.client.get(reverse('agora:course_item_detail', args=[self.assignment.id]))

        self.assertEqual(response.status_code, 200)
        tones_by_id = {submission['id']: submission['status_tone'] for submission in response.context['submissions']}
        self.assertEqual(tones_by_id[submitted.id], 'warning')
        self.assertEqual(tones_by_id[late.id], 'warning')
        self.assertEqual(tones_by_id[reviewed.id], 'accent')
        self.assertEqual(tones_by_id[draft.id], 'neutral')

    def test_teacher_can_review_submission(self):
        submission = Submission.objects.create(
            assignment=self.assignment,
            student=self.student,
            status=Submission.Status.SUBMITTED,
            content='Minha entrega',
        )

        self.client.force_login(self.teacher)

        response = self.client.post(
            reverse('agora:submission_review', args=[submission.id]),
            data={
                'score': '8.5',
                'feedback': 'Boa resolução, mas faltou otimizar uma consulta.',
            },
        )

        self.assertEqual(response.status_code, 302)
        submission.refresh_from_db()
        self.assertEqual(submission.status, Submission.Status.REVIEWED)
        self.assertEqual(float(submission.score), 8.5)
        self.assertEqual(submission.feedback, 'Boa resolução, mas faltou otimizar uma consulta.')
        self.assertEqual(submission.graded_by, self.teacher)
        self.assertIsNotNone(submission.graded_at)

    def test_teacher_can_open_submission_review_form(self):
        submission = Submission.objects.create(
            assignment=self.assignment,
            student=self.student,
            status=Submission.Status.SUBMITTED,
            content='Entrega para revisar',
        )

        self.client.force_login(self.teacher)

        response = self.client.get(reverse('agora:submission_review', args=[submission.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['submission'], submission)
        self.assertEqual(response.context['assignment'], self.assignment)
        self.assertFalse(response.context['is_reviewed'])

    def test_other_teacher_cannot_review_submission(self):
        submission = Submission.objects.create(
            assignment=self.assignment,
            student=self.student,
            status=Submission.Status.SUBMITTED,
            content='Entrega bloqueada',
        )

        self.client.force_login(self.other_teacher)

        response = self.client.post(
            reverse('agora:submission_review', args=[submission.id]),
            data={'score': '9.0', 'feedback': 'Não deveria salvar.'},
        )

        self.assertEqual(response.status_code, 302)
        submission.refresh_from_db()
        self.assertEqual(submission.status, Submission.Status.SUBMITTED)
        self.assertIsNone(submission.score)

    def test_teacher_can_update_existing_review(self):
        submission = Submission.objects.create(
            assignment=self.assignment,
            student=self.student,
            status=Submission.Status.REVIEWED,
            score='7.0',
            feedback='Primeira versão da correção.',
            graded_by=self.teacher,
            content='Minha entrega',
        )

        self.client.force_login(self.teacher)

        response = self.client.post(
            reverse('agora:submission_review', args=[submission.id]),
            data={
                'score': '9.0',
                'feedback': 'Correção atualizada após revisão.',
            },
        )

        self.assertEqual(response.status_code, 302)
        submission.refresh_from_db()
        self.assertEqual(submission.status, Submission.Status.REVIEWED)
        self.assertEqual(float(submission.score), 9.0)
        self.assertEqual(submission.feedback, 'Correção atualizada após revisão.')

    def test_teacher_can_publish_activity(self):
        self.assignment.is_published = False
        self.assignment.save(update_fields=['is_published'])

        self.client.force_login(self.teacher)

        response = self.client.post(reverse('agora:publish_course_item', args=[self.assignment.id]))

        self.assertEqual(response.status_code, 302)
        self.assignment.refresh_from_db()
        self.assertTrue(self.assignment.is_published)

    def test_publish_activity_get_and_foreign_teacher_post_do_not_publish(self):
        self.assignment.is_published = False
        self.assignment.save(update_fields=['is_published'])

        self.client.force_login(self.teacher)
        get_response = self.client.get(reverse('agora:publish_course_item', args=[self.assignment.id]))
        self.assignment.refresh_from_db()

        self.assertEqual(get_response.status_code, 302)
        self.assertFalse(self.assignment.is_published)

        self.client.force_login(self.other_teacher)
        post_response = self.client.post(reverse('agora:publish_course_item', args=[self.assignment.id]))
        self.assignment.refresh_from_db()

        self.assertEqual(post_response.status_code, 302)
        self.assertFalse(self.assignment.is_published)

    def test_publish_activity_is_idempotent(self):
        self.client.force_login(self.teacher)

        first = self.client.post(reverse('agora:publish_course_item', args=[self.assignment.id]))
        second = self.client.post(reverse('agora:publish_course_item', args=[self.assignment.id]))

        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.assignment.refresh_from_db()
        self.assertTrue(self.assignment.is_published)

    def test_course_item_delete_get_and_foreign_teacher_post_do_not_delete(self):
        self.client.force_login(self.teacher)
        get_response = self.client.get(reverse('agora:course_item_delete', args=[self.assignment.id]))

        self.assertEqual(get_response.status_code, 302)
        self.assertTrue(AssignmentItem.objects.filter(pk=self.assignment.id).exists())

        self.client.force_login(self.other_teacher)
        post_response = self.client.post(reverse('agora:course_item_delete', args=[self.assignment.id]))

        self.assertEqual(post_response.status_code, 302)
        self.assertTrue(AssignmentItem.objects.filter(pk=self.assignment.id).exists())

    def test_student_can_submit_quiz_from_detail_page(self):
        self.client.force_login(self.student)

        response = self.client.post(
            reverse('agora:course_item_detail', args=[self.quiz.id]),
            data={
                'action': 'submit_quiz',
                f'question_{self.quiz_question.id}': str(self.correct_quiz_option.id),
                f'question_{self.quiz_question_2.id}': [
                    str(self.quiz_question_2_option_1.id),
                    str(self.quiz_question_2_option_3.id),
                ],
            },
        )

        self.assertEqual(response.status_code, 302)
        answers = list(Answer.objects.filter(quiz=self.quiz, student=self.student).order_by('question__order'))
        self.assertEqual(len(answers), 3)
        self.assertEqual(answers[0].selected_option, self.correct_quiz_option)
        self.assertEqual(
            set(answer.selected_option for answer in answers[1:]),
            {self.quiz_question_2_option_1, self.quiz_question_2_option_3},
        )

    def test_teacher_can_edit_published_quiz_and_clear_student_answers(self):
        Answer.objects.create(
            quiz=self.quiz,
            question=self.quiz_question,
            selected_option=self.correct_quiz_option,
            student=self.student,
        )
        Answer.objects.create(
            quiz=self.quiz,
            question=self.quiz_question_2,
            selected_option=self.quiz_question_2_option_1,
            student=self.student,
        )

        self.client.force_login(self.teacher)

        response = self.client.post(
            reverse('agora:quiz_edit', args=[self.quiz.id]),
            data={
                'activity_kind': 'quiz',
                'module': str(self.module.id),
                'title': 'Quiz atualizado',
                'description': 'Versão revisada.',
                'question_count': '1',
                'question_1_statement': 'Pergunta revisada?',
                'question_1_type': 'single_choice',
                'question_1_score': '8',
                'question_1_option_1': 'Resposta A',
                'question_1_option_1_is_correct': 'on',
                'question_1_option_2': 'Resposta B',
                'question_1_option_3': 'Resposta C',
                'question_1_option_4': 'Resposta D',
                'due_date': '2026-05-10T23:59',
                'allow_resubmissions': 'on',
                'is_published': 'on',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.quiz.refresh_from_db()
        self.assertEqual(self.quiz.title, 'Quiz atualizado')
        self.assertEqual(self.quiz.questions.count(), 1)
        self.assertEqual(Answer.objects.filter(quiz=self.quiz).count(), 0)

    def test_teacher_can_delete_published_quiz(self):
        self.client.force_login(self.teacher)

        response = self.client.post(reverse('agora:quiz_delete', args=[self.quiz.id]))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(QuizItem.objects.filter(pk=self.quiz.id).exists())

    def test_teacher_can_delete_unpublished_quiz(self):
        draft_quiz = QuizItem.objects.create(
            course=self.course,
            module=self.module,
            title='Quiz rascunho',
            description='Ainda não publicado.',
            due_date='2026-05-20T23:59Z',
            max_score=5,
            allow_resubmissions=False,
            is_published=False,
            created_by=self.teacher,
        )

        self.client.force_login(self.teacher)

        response = self.client.post(reverse('agora:quiz_delete', args=[draft_quiz.id]))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(QuizItem.objects.filter(pk=draft_quiz.id).exists())

    def test_course_page_shows_quiz_entry_button_for_students(self):
        self.client.force_login(self.student)

        response = self.client.get(reverse('agora:course_detail', args=[self.course.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Quiz rápido')
        self.assertContains(response, 'Responder ao quiz')
        self.assertNotContains(response, 'Qual comando cria migrations no Django?')

    def test_quiz_detail_shows_one_question_flow_controls(self):
        self.client.force_login(self.student)

        response = self.client.get(reverse('agora:course_item_detail', args=[self.quiz.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Questão 1 de 2')
        self.assertContains(response, 'Próxima questão')
        self.assertContains(response, 'Enviar respostas')
        self.assertContains(response, 'Selecione todas as alternativas corretas.')

    def test_single_attempt_quiz_without_answers_shows_attempt_feedback(self):
        self.quiz.allow_resubmissions = False
        self.quiz.save(update_fields=['allow_resubmissions'])
        self.client.force_login(self.student)

        response = self.client.get(reverse('agora:course_item_detail', args=[self.quiz.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['quiz_feedback'], 'Este quiz aceita apenas uma tentativa.')
        self.assertFalse(response.context['quiz_locked'])

    def test_quiz_submission_rejects_missing_single_choice_answer(self):
        self.client.force_login(self.student)

        response = self.client.post(
            reverse('agora:course_item_detail', args=[self.quiz.id]),
            data={
                'action': 'submit_quiz',
                f'question_{self.quiz_question_2.id}': [
                    str(self.quiz_question_2_option_1.id),
                    str(self.quiz_question_2_option_3.id),
                ],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Responda todas as questões antes de enviar o quiz.')
        self.assertFalse(Answer.objects.filter(quiz=self.quiz, student=self.student).exists())

    def test_quiz_submission_rejects_invalid_multiple_choice_payload(self):
        self.client.force_login(self.student)

        response = self.client.post(
            reverse('agora:course_item_detail', args=[self.quiz.id]),
            data={
                'action': 'submit_quiz',
                f'question_{self.quiz_question.id}': str(self.correct_quiz_option.id),
                f'question_{self.quiz_question_2.id}': [
                    str(self.quiz_question_2_option_1.id),
                    str(self.correct_quiz_option.id),
                ],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Responda todas as questões antes de enviar o quiz.')
        self.assertFalse(Answer.objects.filter(quiz=self.quiz, student=self.student).exists())

    def test_teacher_sees_quiz_answer_counts(self):
        Answer.objects.create(
            quiz=self.quiz,
            question=self.quiz_question,
            selected_option=self.correct_quiz_option,
            student=self.student,
        )

        self.client.force_login(self.teacher)

        response = self.client.get(reverse('agora:course_item_detail', args=[self.quiz.id]))

        self.assertEqual(response.status_code, 200)
        first_question = response.context['quiz_questions'][0]
        counts = {option['id']: option['answer_count'] for option in first_question['options']}
        self.assertEqual(counts[self.correct_quiz_option.id], 1)
        self.assertEqual(counts[self.quiz_option_2.id], 0)

    def test_quiz_score_is_sum_of_correct_question_scores(self):
        Answer.objects.create(
            quiz=self.quiz,
            question=self.quiz_question,
            selected_option=self.correct_quiz_option,
            student=self.student,
        )
        Answer.objects.create(
            quiz=self.quiz,
            question=self.quiz_question_2,
            selected_option=self.quiz_question_2_option_1,
            student=self.student,
        )
        Answer.objects.create(
            quiz=self.quiz,
            question=self.quiz_question_2,
            selected_option=self.quiz_question_2_option_3,
            student=self.student,
        )

        self.client.force_login(self.student)

        response = self.client.get(reverse('agora:course_item_detail', args=[self.quiz.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Pontuação atual: 10.0')

    def test_multi_select_question_requires_exact_set_for_full_marks(self):
        Answer.objects.create(
            quiz=self.quiz,
            question=self.quiz_question_2,
            selected_option=self.quiz_question_2_option_1,
            student=self.student,
        )

        self.client.force_login(self.student)

        response = self.client.get(reverse('agora:course_item_detail', args=[self.quiz.id]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Pontuação atual: 6.0')

    def test_student_cannot_resubmit_when_quiz_disallows_resubmissions(self):
        self.quiz.allow_resubmissions = False
        self.quiz.save(update_fields=['allow_resubmissions'])
        Answer.objects.create(
            quiz=self.quiz,
            question=self.quiz_question,
            selected_option=self.correct_quiz_option,
            student=self.student,
        )
        Answer.objects.create(
            quiz=self.quiz,
            question=self.quiz_question_2,
            selected_option=self.quiz_question_2_option_1,
            student=self.student,
        )

        self.client.force_login(self.student)

        response = self.client.post(
            reverse('agora:course_item_detail', args=[self.quiz.id]),
            data={
                'action': 'submit_quiz',
                f'question_{self.quiz_question.id}': str(self.quiz_option_2.id),
                f'question_{self.quiz_question_2.id}': [
                    str(self.quiz_question_2_option_2.id),
                ],
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Este quiz não permite reenviar respostas.')
        answers = list(Answer.objects.filter(quiz=self.quiz, student=self.student).order_by('question__order'))
        self.assertEqual(answers[0].selected_option, self.correct_quiz_option)

    def test_single_attempt_quiz_renders_saved_answers_as_locked(self):
        self.quiz.allow_resubmissions = False
        self.quiz.save(update_fields=['allow_resubmissions'])
        Answer.objects.create(
            quiz=self.quiz,
            question=self.quiz_question,
            selected_option=self.correct_quiz_option,
            student=self.student,
        )

        self.client.force_login(self.student)

        response = self.client.get(reverse('agora:course_item_detail', args=[self.quiz.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Respostas bloqueadas')
        self.assertContains(response, 'Suas respostas já foram enviadas e este quiz está bloqueado para edição.')
        self.assertContains(response, 'disabled')
        self.assertNotContains(response, 'Enviar respostas')


    def test_teacher_can_edit_unpublished_quiz(self):
        draft_quiz = QuizItem.objects.create(
            course=self.course,
            module=self.module,
            title='Quiz rascunho',
            description='Versão inicial.',
            due_date=timezone.now() + timedelta(days=2),
            max_score=Decimal('1.00'),
            allow_resubmissions=False,
            is_published=False,
            created_by=self.teacher,
        )

        self.client.force_login(self.teacher)

        response = self.client.post(
            reverse('agora:quiz_edit', args=[draft_quiz.id]),
            data={
                'activity_kind': 'quiz',
                'module': str(self.module.id),
                'title': 'Quiz rascunho atualizado',
                'description': 'Versão pronta.',
                'question_count': '1',
                'question_1_statement': 'Pergunta do rascunho?',
                'question_1_type': 'single_choice',
                'question_1_score': '5',
                'question_1_option_1': 'Resposta A',
                'question_1_option_1_is_correct': 'on',
                'question_1_option_2': 'Resposta B',
                'question_1_option_3': 'Resposta C',
                'question_1_option_4': 'Resposta D',
                'due_date': '2026-05-10T23:59',
            },
        )

        self.assertEqual(response.status_code, 302)
        draft_quiz.refresh_from_db()
        self.assertEqual(draft_quiz.title, 'Quiz rascunho atualizado')
        self.assertFalse(draft_quiz.is_published)
        self.assertFalse(draft_quiz.allow_resubmissions)
        self.assertEqual(draft_quiz.questions.count(), 1)

    def test_other_teacher_cannot_edit_quiz(self):
        self.client.force_login(self.other_teacher)

        response = self.client.get(reverse('agora:quiz_edit', args=[self.quiz.id]))

        self.assertEqual(response.status_code, 302)
        self.quiz.refresh_from_db()
        self.assertEqual(self.quiz.title, 'Quiz rápido')
        
class CourseItemInteractionExtraTests(AgoraTestDataMixin, TestCase):
    def setUp(self):
        self.teacher = self.create_user('item-teacher', UserProfile.Role.TEACHER)
        self.other_teacher = self.create_user('item-other-teacher', UserProfile.Role.TEACHER)
        self.student = self.create_user('item-student', UserProfile.Role.STUDENT)
        self.outsider = self.create_user('item-outsider', UserProfile.Role.STUDENT)
        self.course = self.create_course(code='ITEM101', title='Item Course', is_published=True)
        self.module = Module.objects.create(course=self.course, title='Modulo', order=1)
        Enrollment.objects.create(student=self.student, course=self.course, status=Enrollment.Status.ACTIVE)
        self.assignment = AssignmentItem.objects.create(
            course=self.course,
            module=self.module,
            title='Entrega',
            description='Tarefa para envio.',
            due_date=timezone.now() + timedelta(days=1),
            max_score=Decimal('10.00'),
            is_published=True,
            created_by=self.teacher,
        )
        self.forum = ForumItem.objects.create(
            course=self.course,
            module=self.module,
            title='Forum de duvidas',
            description='Espaco de conversa.',
            is_published=True,
            created_by=self.teacher,
        )

    def test_module_create_view_blocks_foreign_teacher_and_duplicate_order(self):
        self.client.force_login(self.other_teacher)
        blocked = self.client.post(
            reverse('agora:module_create', args=[self.course.id]),
            data={'title': 'Modulo 2', 'description': '', 'order': '2'},
        )

        self.assertEqual(blocked.status_code, 302)
        self.assertFalse(Module.objects.filter(course=self.course, title='Modulo 2').exists())

        self.client.force_login(self.teacher)
        duplicate = self.client.post(
            reverse('agora:module_create', args=[self.course.id]),
            data={'title': 'Duplicado', 'description': '', 'order': '1'},
        )

        self.assertEqual(duplicate.status_code, 200)
        self.assertIn('__all__', duplicate.context['form'].errors)

    def test_module_create_view_initializes_next_order_and_creates_module(self):
        self.client.force_login(self.teacher)

        get_response = self.client.get(reverse('agora:module_create', args=[self.course.id]))

        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_response.context['form'].initial['order'], 2)

        post_response = self.client.post(
            reverse('agora:module_create', args=[self.course.id]),
            data={'title': 'Modulo 2', 'description': 'Conteudo novo.', 'order': '2'},
        )

        self.assertEqual(post_response.status_code, 302)
        created_module = Module.objects.get(course=self.course, order=2)
        self.assertEqual(created_module.title, 'Modulo 2')

    def test_student_assignment_submission_rejects_empty_payload_and_saves_valid_payload(self):
        self.client.force_login(self.student)
        empty = self.client.post(
            reverse('agora:course_item_detail', args=[self.assignment.id]),
            data={'action': 'submit_assignment', 'content': ''},
        )

        self.assertEqual(empty.status_code, 200)
        self.assertFalse(Submission.objects.filter(assignment=self.assignment, student=self.student).exists())
        self.assertIn('__all__', empty.context['assignment_form'].errors)

        valid = self.client.post(
            reverse('agora:course_item_detail', args=[self.assignment.id]),
            data={'action': 'submit_assignment', 'content': 'Minha resposta'},
        )

        self.assertEqual(valid.status_code, 302)
        submission = Submission.objects.get(assignment=self.assignment, student=self.student)
        self.assertEqual(submission.status, Submission.Status.SUBMITTED)
        self.assertEqual(submission.content, 'Minha resposta')
        self.assertIsNotNone(submission.submitted_at)

    def test_forum_root_message_reply_and_moderation_flow(self):
        self.client.force_login(self.student)
        root_response = self.client.post(
            reverse('agora:course_item_detail', args=[self.forum.id]),
            data={'action': 'post_forum_message', 'content': 'Duvida inicial'},
        )

        self.assertEqual(root_response.status_code, 302)
        root = ForumMessage.objects.get(forum=self.forum, content='Duvida inicial')
        reply_response = self.client.post(
            reverse('agora:course_item_detail', args=[self.forum.id]),
            data={'action': 'post_forum_message', 'content': 'Complemento', 'parent_id': str(root.id)},
        )

        self.assertEqual(reply_response.status_code, 302)
        reply = ForumMessage.objects.get(forum=self.forum, content='Complemento')
        self.assertEqual(reply.parent, root)

        self.client.force_login(self.outsider)
        blocked = self.client.post(
            reverse('agora:course_item_detail', args=[self.forum.id]),
            data={'action': 'post_forum_message', 'content': 'Nao matriculado'},
        )
        self.assertEqual(blocked.status_code, 302)
        self.assertFalse(ForumMessage.objects.filter(content='Nao matriculado').exists())

        self.client.force_login(self.teacher)
        deleted = self.client.post(reverse('agora:delete_forum_message', args=[root.id]))
        self.assertEqual(deleted.status_code, 302)
        self.assertFalse(ForumMessage.objects.filter(pk=root.id).exists())
        self.assertFalse(ForumMessage.objects.filter(pk=reply.id).exists())

    def test_forum_detail_builds_nested_threads_and_rejects_blank_message(self):
        root = ForumMessage.objects.create(forum=self.forum, author=self.student, content='Pergunta raiz')
        reply = ForumMessage.objects.create(
            forum=self.forum,
            author=self.teacher,
            content='Resposta do professor',
            parent=root,
        )
        nested_reply = ForumMessage.objects.create(
            forum=self.forum,
            author=self.student,
            content='Obrigado pela resposta',
            parent=reply,
        )

        self.client.force_login(self.student)
        response = self.client.get(reverse('agora:course_item_detail', args=[self.forum.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['forum_message_count'], 3)
        threads = response.context['forum_threads']
        self.assertEqual(len(threads), 1)
        self.assertEqual(threads[0]['content'], 'Pergunta raiz')
        self.assertEqual(threads[0]['depth'], 0)
        self.assertEqual(threads[0]['children'][0]['content'], 'Resposta do professor')
        self.assertEqual(threads[0]['children'][0]['depth'], 1)
        self.assertEqual(threads[0]['children'][0]['children'][0]['content'], 'Obrigado pela resposta')
        self.assertEqual(threads[0]['children'][0]['children'][0]['depth'], 2)

        blank_response = self.client.post(
            reverse('agora:course_item_detail', args=[self.forum.id]),
            data={'action': 'post_forum_message', 'content': '   '},
        )

        self.assertEqual(blank_response.status_code, 200)
        self.assertIn('content', blank_response.context['forum_form'].errors)
        self.assertEqual(ForumMessage.objects.filter(forum=self.forum).count(), 3)

    def test_teacher_can_open_forum_form_and_post_message(self):
        self.client.force_login(self.teacher)

        get_response = self.client.get(reverse('agora:course_item_detail', args=[self.forum.id]))

        self.assertEqual(get_response.status_code, 200)
        self.assertIsInstance(get_response.context['forum_form'], ForumMessageForm)

        post_response = self.client.post(
            reverse('agora:course_item_detail', args=[self.forum.id]),
            data={'action': 'post_forum_message', 'content': 'Orientação do professor'},
        )

        self.assertEqual(post_response.status_code, 302)
        message = ForumMessage.objects.get(forum=self.forum, content='Orientação do professor')
        self.assertEqual(message.author, self.teacher)
        self.assertIsNone(message.parent)

    def test_forum_post_rejects_parent_from_other_forum(self):
        other_forum = ForumItem.objects.create(
            course=self.course,
            module=self.module,
            title='Outro forum',
            description='Outro.',
            is_published=True,
            created_by=self.teacher,
        )
        parent = ForumMessage.objects.create(forum=other_forum, author=self.teacher, content='Mensagem externa')
        self.client.force_login(self.student)

        response = self.client.post(
            reverse('agora:course_item_detail', args=[self.forum.id]),
            data={'action': 'post_forum_message', 'content': 'Resposta invalida', 'parent_id': str(parent.id)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('__all__', response.context['forum_form'].errors)
        self.assertFalse(ForumMessage.objects.filter(forum=self.forum, content='Resposta invalida').exists())

    def test_forum_delete_views_handle_non_post_and_unauthorized_message_moderation(self):
        message = ForumMessage.objects.create(forum=self.forum, author=self.student, content='Mensagem a moderar')

        self.client.force_login(self.teacher)
        get_message_response = self.client.get(reverse('agora:delete_forum_message', args=[message.id]))
        self.assertEqual(get_message_response.status_code, 302)
        self.assertEqual(get_message_response.url, reverse('agora:index'))
        self.assertTrue(ForumMessage.objects.filter(pk=message.id).exists())

        get_forum_response = self.client.get(reverse('agora:delete_forum', args=[self.forum.id]))
        self.assertEqual(get_forum_response.status_code, 302)
        self.assertTrue(ForumItem.objects.filter(pk=self.forum.id).exists())

        self.client.force_login(self.other_teacher)
        unauthorized_response = self.client.post(reverse('agora:delete_forum_message', args=[message.id]))
        self.assertEqual(unauthorized_response.status_code, 302)
        self.assertTrue(ForumMessage.objects.filter(pk=message.id).exists())

    def test_quiz_submission_with_missing_answers_does_not_create_partial_answers(self):
        quiz_data = self.create_quiz_with_questions(course=self.course, module=self.module, title='Quiz incompleto')
        self.client.force_login(self.student)

        response = self.client.post(
            reverse('agora:course_item_detail', args=[quiz_data['quiz'].id]),
            data={
                'action': 'submit_quiz',
                f'question_{quiz_data["single"].id}': str(quiz_data['single_correct'].id),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Responda todas as questões antes de enviar o quiz.')
        self.assertFalse(Answer.objects.filter(quiz=quiz_data['quiz'], student=self.student).exists())

    def test_teacher_can_delete_forum_but_other_teacher_cannot(self):
        self.client.force_login(self.other_teacher)
        blocked = self.client.post(reverse('agora:delete_forum', args=[self.forum.id]))
        self.assertEqual(blocked.status_code, 302)
        self.assertTrue(ForumItem.objects.filter(pk=self.forum.id).exists())

        self.client.force_login(self.teacher)
        deleted = self.client.post(reverse('agora:delete_forum', args=[self.forum.id]))
        self.assertEqual(deleted.status_code, 302)
        self.assertFalse(ForumItem.objects.filter(pk=self.forum.id).exists())
