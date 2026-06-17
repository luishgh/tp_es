from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.utils import timezone

from agora.models import (
    Answer,
    AssignmentItem,
    Course,
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
)
from agora.tests.helpers import AgoraTestDataMixin
from agora.views import auth, common, course_items, courses, dashboard


def attach_session_and_messages(request):
    middleware = SessionMiddleware(lambda req: None)
    middleware.process_request(request)
    request.session.save()
    setattr(request, '_messages', FallbackStorage(request))
    return request


def capture_render(*args, **kwargs):
    response = HttpResponse('ok')
    response.context_data = args[2]
    response.template_name = args[1]
    return response


class CommonViewHelperUnitTests(TestCase):
    def test_configure_time_locale_tries_fallbacks_until_success(self):
        calls = []

        def fake_setlocale(category, locale_name):
            calls.append(locale_name)
            if locale_name != 'Portuguese_Brazil.1252':
                raise common.locale.Error('unsupported locale')
            return locale_name

        with patch('agora.views.common.locale.setlocale', side_effect=fake_setlocale):
            common._configure_time_locale()

        self.assertEqual(
            calls,
            ['pt_BR.UTF-8', 'pt_BR.utf8', 'Portuguese_Brazil.1252'],
        )

    def test_user_role_defaults_to_student_when_profile_is_missing(self):
        anonymous_like = SimpleNamespace()
        teacher_like = SimpleNamespace(profile=SimpleNamespace(role=UserProfile.Role.TEACHER))

        self.assertEqual(common._user_role(anonymous_like), UserProfile.Role.STUDENT)
        self.assertEqual(common._user_role(teacher_like), UserProfile.Role.TEACHER)


class AuthHelperUnitTests(AgoraTestDataMixin, TestCase):
    def setUp(self):
        self.teacher = self.create_user('auth-helper-teacher', UserProfile.Role.TEACHER)
        self.student = self.create_user('auth-helper-student', UserProfile.Role.STUDENT)

    def test_authenticate_by_username_or_academic_id_accepts_both_identifiers(self):
        request = RequestFactory().post('/login/')

        by_username = auth._authenticate_by_username_or_academic_id(
            request=request,
            identifier=self.student.username,
            password=self.password,
        )
        by_academic_id = auth._authenticate_by_username_or_academic_id(
            request=request,
            identifier=self.student.profile.academic_id,
            password=self.password,
        )
        invalid = auth._authenticate_by_username_or_academic_id(
            request=request,
            identifier='missing-user',
            password=self.password,
        )

        self.assertEqual(by_username, self.student)
        self.assertEqual(by_academic_id, self.student)
        self.assertIsNone(invalid)


class DashboardAndCoursesUnitTests(AgoraTestDataMixin, TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.teacher = self.create_user('view-teacher', UserProfile.Role.TEACHER)
        self.student = self.create_user('view-student', UserProfile.Role.STUDENT)
        self.other_student = self.create_user('view-student-2', UserProfile.Role.STUDENT)
        self.course = self.create_course(teacher=self.teacher, code='DASH101', title='Dashboard')
        self.module = Module.objects.create(course=self.course, title='Modulo 1', order=1)
        self.active_enrollment = Enrollment.objects.create(
            student=self.student,
            course=self.course,
            status=Enrollment.Status.ACTIVE,
        )

    def test_teacher_dashboard_context_includes_progress_and_pending_reviews(self):
        past_due = timezone.now() - timedelta(days=1)
        assignment = AssignmentItem.objects.create(
            course=self.course,
            module=self.module,
            title='Lista 1',
            description='Atividade.',
            due_date=past_due,
            max_score=Decimal('10.00'),
            is_published=True,
            created_by=self.teacher,
        )
        Submission.objects.create(
            assignment=assignment,
            student=self.student,
            status=Submission.Status.SUBMITTED,
            content='Entrega pendente',
            submitted_at=timezone.now() - timedelta(hours=3),
        )
        Submission.objects.create(
            assignment=assignment,
            student=self.other_student,
            status=Submission.Status.REVIEWED,
            content='Entrega corrigida',
            submitted_at=timezone.now() - timedelta(hours=4),
            score=Decimal('9.00'),
            graded_by=self.teacher,
            graded_at=timezone.now() - timedelta(hours=2),
        )
        Enrollment.objects.create(
            student=self.other_student,
            course=self.course,
            status=Enrollment.Status.ACTIVE,
        )

        context = dashboard._build_teacher_dashboard_context(self.teacher)

        self.assertEqual(context['courses_count'], 1)
        self.assertEqual(context['pending_count'], 1)
        self.assertEqual(context['course_cards'][0]['progress'], 50)
        self.assertIn('2 alunos ativos', context['course_cards'][0]['meta_label'])
        self.assertEqual(context['pending_cards'][0]['title'], 'Lista 1')

    def test_student_dashboard_context_categorizes_pending_work(self):
        overdue = AssignmentItem.objects.create(
            course=self.course,
            module=self.module,
            title='Atrasada',
            description='A.',
            due_date=timezone.now() - timedelta(days=1),
            max_score=Decimal('10.00'),
            is_published=True,
            created_by=self.teacher,
        )
        due_today = AssignmentItem.objects.create(
            course=self.course,
            module=self.module,
            title='Hoje',
            description='H.',
            due_date=timezone.now() + timedelta(hours=2),
            max_score=Decimal('10.00'),
            is_published=True,
            created_by=self.teacher,
        )
        upcoming = QuizItem.objects.create(
            course=self.course,
            module=self.module,
            title='Quiz proximo',
            description='Q.',
            due_date=timezone.now() + timedelta(days=2),
            max_score=Decimal('5.00'),
            is_published=True,
            created_by=self.teacher,
        )
        no_due_date = QuizItem.objects.create(
            course=self.course,
            module=self.module,
            title='Sem prazo',
            description='S.',
            due_date=None,
            max_score=Decimal('5.00'),
            is_published=True,
            created_by=self.teacher,
        )
        Submission.objects.create(
            assignment=overdue,
            student=self.student,
            status=Submission.Status.REVIEWED,
            content='Ja enviada',
            score=Decimal('8.00'),
            graded_by=self.teacher,
            graded_at=timezone.now(),
        )
        question = QuizQuestion.objects.create(
            quiz=upcoming,
            statement='Pergunta?',
            order=1,
            weight=Decimal('5.00'),
        )
        option = QuizOption.objects.create(question=question, text='A', is_correct=True, order=1)
        Answer.objects.create(quiz=upcoming, question=question, selected_option=option, student=self.student)

        context = dashboard._build_student_dashboard_context(self.student)

        self.assertEqual(context['courses_count'], 1)
        self.assertEqual(context['pending_count'], 2)
        self.assertEqual(context['overdue_activities'], 0)
        self.assertEqual(context['course_cards'][0]['progress'], 50)
        self.assertEqual(
            {item['title']: item['status_label'] for item in context['pending_cards']},
            {'Hoje': 'Vence hoje', 'Sem prazo': 'Sem prazo'},
        )
        self.assertEqual(context['course_cards'][0]['progress_label'], '2 atividades pendentes')
        self.assertIsNotNone(no_due_date)

    def test_courses_helpers_compute_due_dates_and_scores(self):
        resource = ResourceItem.objects.create(
            course=self.course,
            module=self.module,
            title='Material',
            description='Link.',
            attachment_url='https://example.com/material',
            created_by=self.teacher,
        )
        quiz = QuizItem.objects.create(
            course=self.course,
            module=self.module,
            title='Quiz',
            description='Teste.',
            due_date=timezone.now(),
            max_score=Decimal('10.00'),
            is_published=True,
            created_by=self.teacher,
        )
        single = QuizQuestion.objects.create(
            quiz=quiz,
            statement='Uma resposta?',
            order=1,
            weight=Decimal('4.00'),
        )
        single_right = QuizOption.objects.create(question=single, text='Correta', is_correct=True, order=1)
        QuizOption.objects.create(question=single, text='Errada', is_correct=False, order=2)
        multi = QuizQuestion.objects.create(
            quiz=quiz,
            statement='Multipla?',
            question_type=QuizQuestion.QuestionType.MULTIPLE_CHOICE,
            order=2,
            weight=Decimal('6.00'),
        )
        multi_a = QuizOption.objects.create(question=multi, text='A', is_correct=True, order=1)
        QuizOption.objects.create(question=multi, text='B', is_correct=False, order=2)
        multi_c = QuizOption.objects.create(question=multi, text='C', is_correct=True, order=3)
        answers = [
            Answer(quiz=quiz, question=single, selected_option=single_right, student=self.student),
            Answer(quiz=quiz, question=multi, selected_option=multi_a, student=self.student),
            Answer(quiz=quiz, question=multi, selected_option=multi_c, student=self.student),
        ]

        self.assertIsNone(courses._detail_due_date(resource))
        self.assertTrue(courses._question_is_correct(single, {single_right.id}))
        self.assertEqual(courses._calculate_quiz_score([single, multi], answers), 10.0)
        self.assertEqual(
            courses._calculate_default_final_grade(
                [{'score': Decimal('4.50')}, {'score': None}, {'score': 3}],
            ),
            Decimal('7.50'),
        )

    def test_course_performance_view_builds_student_cards_and_updates_final_grade(self):
        assignment = AssignmentItem.objects.create(
            course=self.course,
            module=self.module,
            title='Lista',
            description='Entrega.',
            due_date=timezone.now() - timedelta(days=1),
            max_score=Decimal('10.00'),
            is_published=True,
            created_by=self.teacher,
        )
        Submission.objects.create(
            assignment=assignment,
            student=self.student,
            status=Submission.Status.REVIEWED,
            content='Texto',
            submitted_at=timezone.now() - timedelta(days=1),
            score=Decimal('7.50'),
            feedback='Bom',
            graded_by=self.teacher,
            graded_at=timezone.now() - timedelta(hours=6),
        )
        quiz_data = self.create_quiz_with_questions(course=self.course, module=self.module, title='Quiz perf')
        Answer.objects.create(
            quiz=quiz_data['quiz'],
            question=quiz_data['single'],
            selected_option=quiz_data['single_correct'],
            student=self.student,
        )
        Answer.objects.create(
            quiz=quiz_data['quiz'],
            question=quiz_data['multi'],
            selected_option=quiz_data['multi_correct_a'],
            student=self.student,
        )
        Answer.objects.create(
            quiz=quiz_data['quiz'],
            question=quiz_data['multi'],
            selected_option=quiz_data['multi_correct_c'],
            student=self.student,
        )

        get_request = attach_session_and_messages(
            self.factory.get(f'/cursos/{self.course.id}/desempenho/')
        )
        get_request.user = self.teacher

        with patch('agora.views.courses.render', side_effect=capture_render):
            response = courses.course_performance_view(get_request, self.course.id)

        student_card = response.context_data['student_cards_page'].object_list[0]
        self.assertEqual(response.context_data['student_count'], 1)
        self.assertEqual(student_card['delivered_count'], 2)
        self.assertEqual(student_card['graded_count'], 2)
        self.assertEqual(student_card['average_score'], 8.75)
        self.assertEqual(student_card['suggested_final_grade'], Decimal('17.50'))

        post_request = attach_session_and_messages(
            self.factory.post(
                f'/cursos/{self.course.id}/desempenho/',
                data={
                    'action': 'update_final_grade',
                    'enrollment_id': self.active_enrollment.id,
                    'student_page': '1',
                    f'enrollment-{self.active_enrollment.id}-final_grade': '9.25',
                },
            )
        )
        post_request.user = self.teacher

        response = courses.course_performance_view(post_request, self.course.id)
        self.active_enrollment.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.active_enrollment.final_grade, Decimal('9.25'))

    def test_enrollment_and_publish_views_handle_state_transitions(self):
        cancelled = Enrollment.objects.create(
            student=self.other_student,
            course=self.course,
            status=Enrollment.Status.CANCELLED,
        )
        student_request = attach_session_and_messages(
            self.factory.post(f'/cursos/{self.course.id}/solicitar-matricula/')
        )
        student_request.user = self.other_student
        response = courses.request_enrollment_view(student_request, self.course.id)
        cancelled.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(cancelled.status, Enrollment.Status.PENDING)
        self.assertIsNone(cancelled.final_grade)

        decision_request = attach_session_and_messages(
            self.factory.post(f'/matriculas/{cancelled.id}/accept/')
        )
        decision_request.user = self.teacher
        response = courses.enrollment_decision_view(decision_request, cancelled.id, 'accept')
        cancelled.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(cancelled.status, Enrollment.Status.ACTIVE)

        self.course.is_published = False
        self.course.save(update_fields=['is_published'])
        publish_request = attach_session_and_messages(
            self.factory.post(f'/cursos/{self.course.id}/publicar/')
        )
        publish_request.user = self.teacher
        response = courses.publish_course_view(publish_request, self.course.id)
        self.course.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.course.is_published)

    def test_courses_hub_view_builds_teacher_and_student_contexts(self):
        Enrollment.objects.create(
            student=self.other_student,
            course=self.course,
            status=Enrollment.Status.PENDING,
        )
        teacher_request = attach_session_and_messages(self.factory.get('/cursos/'))
        teacher_request.user = self.teacher

        with patch('agora.views.courses.render', side_effect=capture_render):
            teacher_response = courses.courses_hub_view(teacher_request)

        self.assertEqual(teacher_response.context_data['taught_courses_count'], 1)
        self.assertEqual(teacher_response.context_data['pending_requests_count'], 1)

        create_request = attach_session_and_messages(
            self.factory.post(
                '/cursos/',
                data={
                    'action': 'create_course',
                    'code': 'NEW101',
                    'title': 'Novo curso',
                    'description': 'Descricao',
                    'syllabus': 'Ementa',
                    'workload_hours': '30',
                    'is_published': 'on',
                },
            )
        )
        create_request.user = self.teacher
        create_response = courses.courses_hub_view(create_request)

        self.assertEqual(create_response.status_code, 302)
        self.assertTrue(Course.objects.filter(code='NEW101', teacher=self.teacher).exists())

        pending_course = self.create_course(teacher=self.teacher, code='PEN101', title='Pendente')
        completed_course = self.create_course(teacher=self.teacher, code='COM101', title='Completo')
        cancelled_course = self.create_course(teacher=self.teacher, code='CAN101', title='Cancelado')
        Enrollment.objects.create(student=self.student, course=pending_course, status=Enrollment.Status.PENDING)
        Enrollment.objects.create(student=self.student, course=completed_course, status=Enrollment.Status.COMPLETED)
        Enrollment.objects.create(student=self.student, course=cancelled_course, status=Enrollment.Status.CANCELLED)

        student_request = attach_session_and_messages(self.factory.get('/cursos/'))
        student_request.user = self.student

        with patch('agora.views.courses.render', side_effect=capture_render):
            student_response = courses.courses_hub_view(student_request)

        cards = student_response.context_data['available_courses_page'].paginator.object_list
        badges = {card['code']: card['status_badge'] for card in cards}
        self.assertEqual(student_response.context_data['available_courses_count'], 4)
        self.assertEqual(badges['PEN101'], 'Aguardando aprovação')
        self.assertEqual(badges['COM101'], 'Concluído')
        self.assertEqual(badges['CAN101'], 'Solicitação recusada')

    def test_course_detail_view_filters_visibility_for_teacher_and_student(self):
        published_assignment = AssignmentItem.objects.create(
            course=self.course,
            module=self.module,
            title='Publicada',
            description='Entrega.',
            due_date=timezone.now(),
            max_score=Decimal('10.00'),
            is_published=True,
            created_by=self.teacher,
        )
        unpublished_assignment = AssignmentItem.objects.create(
            course=self.course,
            module=self.module,
            title='Oculta',
            description='Entrega.',
            due_date=timezone.now() + timedelta(days=1),
            max_score=Decimal('10.00'),
            is_published=False,
            created_by=self.teacher,
        )
        ResourceItem.objects.create(
            course=self.course,
            title='Sem modulo',
            description='Recurso.',
            attachment_url='https://example.com/recurso',
            is_published=True,
            created_by=self.teacher,
        )
        Submission.objects.create(
            assignment=published_assignment,
            student=self.student,
            status=Submission.Status.SUBMITTED,
            content='Entrega',
        )
        Submission.objects.create(
            assignment=unpublished_assignment,
            student=self.other_student,
            status=Submission.Status.SUBMITTED,
            content='Entrega 2',
        )

        teacher_request = attach_session_and_messages(self.factory.get(f'/cursos/{self.course.id}/'))
        teacher_request.user = self.teacher
        with patch('agora.views.courses.render', side_effect=capture_render):
            teacher_response = courses.course_detail_view(teacher_request, self.course.id)

        modules_page = teacher_response.context_data['modules_page'].object_list
        self.assertEqual(teacher_response.context_data['student_count'], 1)
        self.assertEqual(teacher_response.context_data['modules_count'], 2)
        self.assertTrue(
            any(activity['title'] == 'Oculta' for module in modules_page for activity in module['activities'])
        )

        student_request = attach_session_and_messages(self.factory.get(f'/cursos/{self.course.id}/'))
        student_request.user = self.student
        with patch('agora.views.courses.render', side_effect=capture_render):
            student_response = courses.course_detail_view(student_request, self.course.id)

        student_modules = student_response.context_data['modules_page'].object_list
        titles = [activity['title'] for module in student_modules for activity in module['activities']]
        self.assertIn('Publicada', titles)
        self.assertNotIn('Oculta', titles)

        outsider = self.create_user('outsider-student', UserProfile.Role.STUDENT)
        outsider_request = attach_session_and_messages(self.factory.get(f'/cursos/{self.course.id}/'))
        outsider_request.user = outsider
        denied_response = courses.course_detail_view(outsider_request, self.course.id)
        self.assertEqual(denied_response.status_code, 302)


class CourseItemsUnitTests(AgoraTestDataMixin, TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.teacher = self.create_user('item-teacher', UserProfile.Role.TEACHER)
        self.student = self.create_user('item-student', UserProfile.Role.STUDENT)
        self.course = self.create_course(teacher=self.teacher, code='ITM101', title='Itens')
        self.module = Module.objects.create(course=self.course, title='Modulo 1', order=1)
        Enrollment.objects.create(student=self.student, course=self.course, status=Enrollment.Status.ACTIVE)

    def test_build_forum_message_tree_and_submission_handler(self):
        forum = ForumItem.objects.create(
            course=self.course,
            module=self.module,
            title='Forum',
            description='Debate.',
            is_published=True,
            created_by=self.teacher,
        )
        root = ForumMessage.objects.create(forum=forum, author=self.teacher, content='Mensagem raiz')
        reply = ForumMessage.objects.create(forum=forum, author=self.student, parent=root, content='Resposta')

        tree = course_items._build_forum_message_tree(
            ForumMessage.objects.filter(forum=forum).select_related('author').order_by('created_at', 'id')
        )

        self.assertEqual(len(tree), 1)
        self.assertEqual(tree[0]['id'], root.id)
        self.assertEqual(tree[0]['children'][0]['id'], reply.id)
        self.assertEqual(tree[0]['children'][0]['depth'], 1)

        request = attach_session_and_messages(
            self.factory.post(
                f'/itens/{forum.id}/',
                data={'content': 'Nova mensagem', 'action': 'post_forum_message'},
            )
        )
        request.user = self.student

        response = course_items._handle_forum_message_submission(
            request,
            forum=forum,
            user=self.student,
            course_item_id=forum.id,
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(forum.messages.filter(content='Nova mensagem', parent__isnull=True).exists())

        invalid_parent_request = attach_session_and_messages(
            self.factory.post(
                f'/itens/{forum.id}/',
                data={'content': 'Resposta', 'parent_id': '999999', 'action': 'post_forum_message'},
            )
        )
        invalid_parent_request.user = self.student
        invalid_result = course_items._handle_forum_message_submission(
            invalid_parent_request,
            forum=forum,
            user=self.student,
            course_item_id=forum.id,
        )
        self.assertTrue(hasattr(invalid_result, 'errors'))
        self.assertIn('__all__', invalid_result.errors)

    def test_course_item_detail_view_handles_material_quiz_and_submission_review(self):
        resource = ResourceItem.objects.create(
            course=self.course,
            module=self.module,
            title='Slides',
            description='Material.',
            attachment_url='https://example.com/slides',
            is_published=True,
            created_by=self.teacher,
        )
        assignment = AssignmentItem.objects.create(
            course=self.course,
            module=self.module,
            title='Lista',
            description='Entrega.',
            due_date=timezone.now(),
            max_score=Decimal('10.00'),
            is_published=True,
            created_by=self.teacher,
        )
        quiz_data = self.create_quiz_with_questions(course=self.course, module=self.module, title='Quiz aluno')
        forum = ForumItem.objects.create(
            course=self.course,
            module=self.module,
            title='Forum 2',
            description='Debate.',
            is_published=True,
            created_by=self.teacher,
        )
        submission = Submission.objects.create(
            assignment=assignment,
            student=self.student,
            status=Submission.Status.SUBMITTED,
            content='Entrega inicial',
            submitted_at=timezone.now(),
        )
        ForumMessage.objects.create(forum=forum, author=self.teacher, content='Topico')

        with patch('agora.views.course_items.render', side_effect=capture_render):
            material_request = attach_session_and_messages(self.factory.get(f'/itens/{resource.id}/'))
            material_request.user = self.student
            material_response = course_items.course_item_detail_view(material_request, resource.id)

            self.assertEqual(material_response.context_data['material_actions'][0]['label'], 'Abrir link')

            quiz_post = attach_session_and_messages(
                self.factory.post(
                    f'/itens/{quiz_data["quiz"].id}/',
                    data={
                        'action': 'submit_quiz',
                        f'question_{quiz_data["single"].id}': str(quiz_data["single_correct"].id),
                        f'question_{quiz_data["multi"].id}': [
                            str(quiz_data["multi_correct_a"].id),
                            str(quiz_data["multi_correct_c"].id),
                        ],
                    },
                )
            )
            quiz_post.user = self.student
            quiz_response = course_items.course_item_detail_view(quiz_post, quiz_data['quiz'].id)
            self.assertEqual(quiz_response.status_code, 302)

            forum_request = attach_session_and_messages(self.factory.get(f'/itens/{forum.id}/'))
            forum_request.user = self.teacher
            forum_response = course_items.course_item_detail_view(forum_request, forum.id)
            self.assertEqual(forum_response.context_data['forum_message_count'], 1)

        review_request = attach_session_and_messages(
            self.factory.post(
                f'/submissoes/{submission.id}/avaliar/',
                data={'score': '9.00', 'feedback': 'Corrigido'},
            )
        )
        review_request.user = self.teacher

        response = course_items.submission_review_view(review_request, submission.id)
        submission.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(submission.status, Submission.Status.REVIEWED)
        self.assertEqual(submission.score, Decimal('9.00'))

    def test_course_item_helpers_create_edit_and_delete_flows(self):
        self.assertIn('quiz', course_items.ACTIVITY_CREATE_CONFIG)

        module_get = attach_session_and_messages(
            self.factory.get(f'/cursos/{self.course.id}/modulos/criar/')
        )
        module_get.user = self.teacher
        with patch('agora.views.course_items.render', side_effect=capture_render):
            response = course_items.module_create_view(module_get, self.course.id)
        self.assertEqual(response.context_data['form_title'], 'Criar Novo Módulo')

        module_post = attach_session_and_messages(
            self.factory.post(
                f'/cursos/{self.course.id}/modulos/criar/',
                data={'title': 'Modulo novo', 'description': 'Desc', 'order': '2'},
            )
        )
        module_post.user = self.teacher
        response = course_items.module_create_view(module_post, self.course.id)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Module.objects.filter(course=self.course, title='Modulo novo').exists())

        create_get = attach_session_and_messages(
            self.factory.get(f'/cursos/{self.course.id}/itens/criar/?type=invalid')
        )
        create_get.user = self.teacher
        with patch('agora.views.course_items.render', side_effect=capture_render):
            response = course_items.course_item_create_view(create_get, self.course.id)
        self.assertEqual(response.context_data['selected_type'], 'resource')

        create_post = attach_session_and_messages(
            self.factory.post(
                f'/cursos/{self.course.id}/itens/criar/',
                data={
                    'activity_kind': 'resource',
                    'module': str(self.module.id),
                    'title': 'Material criado',
                    'description': 'Descricao',
                    'attachment_url': 'https://example.com/novo',
                    'is_published': 'on',
                },
            )
        )
        create_post.user = self.teacher
        response = course_items.course_item_create_view(create_post, self.course.id)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ResourceItem.objects.filter(course=self.course, title='Material criado').exists())

        quiz = QuizItem.objects.create(
            course=self.course,
            module=self.module,
            title='Quiz editar',
            description='Editar.',
            due_date=timezone.now(),
            max_score=Decimal('4.00'),
            is_published=True,
            created_by=self.teacher,
        )
        editable_question = QuizQuestion.objects.create(
            quiz=quiz,
            statement='Pergunta inicial?',
            order=1,
            weight=Decimal('4.00'),
        )
        editable_options = [
            QuizOption.objects.create(question=editable_question, text='A', is_correct=True, order=1),
            QuizOption.objects.create(question=editable_question, text='B', is_correct=False, order=2),
            QuizOption.objects.create(question=editable_question, text='C', is_correct=False, order=3),
            QuizOption.objects.create(question=editable_question, text='D', is_correct=False, order=4),
        ]
        Answer.objects.create(
            quiz=quiz,
            question=editable_question,
            selected_option=editable_options[0],
            student=self.student,
        )

        edit_get = attach_session_and_messages(
            self.factory.get(f'/itens/{quiz.id}/quiz/editar/')
        )
        edit_get.user = self.teacher
        with patch('agora.views.course_items.render', side_effect=capture_render):
            response = course_items.quiz_edit_view(edit_get, quiz.id)
        self.assertTrue(response.context_data['is_edit_mode'])

        edit_post = attach_session_and_messages(
            self.factory.post(
                f'/itens/{quiz.id}/quiz/editar/',
                data={
                    'module': str(self.module.id),
                    'title': 'Quiz atualizado',
                    'description': 'Atualizado',
                    'allow_resubmissions': 'on',
                    'is_published': 'on',
                    'question_count': '1',
                    'question_1_statement': 'Nova?',
                    'question_1_type': QuizQuestion.QuestionType.SINGLE_CHOICE,
                    'question_1_score': '3',
                    'question_1_option_1': 'A',
                    'question_1_option_1_is_correct': 'on',
                    'question_1_option_2': 'B',
                    'question_1_option_3': 'C',
                    'question_1_option_4': 'D',
                    'due_date_date': '2026-05-01',
                    'due_date_time': '10:00',
                },
            )
        )
        edit_post.user = self.teacher
        response = course_items.quiz_edit_view(edit_post, quiz.id)
        quiz.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(quiz.title, 'Quiz atualizado')
        self.assertFalse(Answer.objects.filter(quiz=quiz).exists())

        delete_get = attach_session_and_messages(
            self.factory.get(f'/itens/{quiz.id}/excluir/')
        )
        delete_get.user = self.teacher
        response = course_items.course_item_delete_view(delete_get, quiz.id)
        self.assertEqual(response.status_code, 302)

        delete_post = attach_session_and_messages(
            self.factory.post(f'/itens/{quiz.id}/excluir/')
        )
        delete_post.user = self.teacher
        response = course_items.course_item_delete_view(delete_post, quiz.id)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(QuizItem.objects.filter(pk=quiz.id).exists())

    def test_course_item_detail_view_covers_assignment_and_permission_branches(self):
        assignment = AssignmentItem.objects.create(
            course=self.course,
            module=self.module,
            title='Lista aluno',
            description='Entrega.',
            due_date=timezone.now(),
            max_score=Decimal('10.00'),
            is_published=True,
            created_by=self.teacher,
        )
        unpublished_resource = ResourceItem.objects.create(
            course=self.course,
            module=self.module,
            title='Oculto',
            description='Recurso oculto.',
            attachment_url='https://example.com/hidden',
            is_published=False,
            created_by=self.teacher,
        )

        get_request = attach_session_and_messages(self.factory.get(f'/itens/{assignment.id}/'))
        get_request.user = self.student
        with patch('agora.views.course_items.render', side_effect=capture_render):
            response = course_items.course_item_detail_view(get_request, assignment.id)
        self.assertEqual(response.context_data['submission_status']['label'], 'Não iniciado')

        post_request = attach_session_and_messages(
            self.factory.post(
                f'/itens/{assignment.id}/',
                data={'action': 'submit_assignment', 'content': 'Minha entrega'},
            )
        )
        post_request.user = self.student
        response = course_items.course_item_detail_view(post_request, assignment.id)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Submission.objects.filter(assignment=assignment, student=self.student).exists())

        outsider = self.create_user('item-outsider', UserProfile.Role.STUDENT)
        denied_request = attach_session_and_messages(self.factory.get(f'/itens/{assignment.id}/'))
        denied_request.user = outsider
        denied = course_items.course_item_detail_view(denied_request, assignment.id)
        self.assertEqual(denied.status_code, 302)

        unpublished_request = attach_session_and_messages(self.factory.get(f'/itens/{unpublished_resource.id}/'))
        unpublished_request.user = self.student
        unpublished = course_items.course_item_detail_view(unpublished_request, unpublished_resource.id)
        self.assertEqual(unpublished.status_code, 302)

    def test_publish_and_delete_views_update_course_items_and_forum_messages(self):
        assignment = AssignmentItem.objects.create(
            course=self.course,
            module=self.module,
            title='Nao publicado',
            description='Entrega.',
            due_date=timezone.now(),
            max_score=Decimal('10.00'),
            is_published=False,
            created_by=self.teacher,
        )
        forum = ForumItem.objects.create(
            course=self.course,
            module=self.module,
            title='Forum delete',
            description='Debate.',
            is_published=True,
            created_by=self.teacher,
        )
        message = ForumMessage.objects.create(forum=forum, author=self.student, content='Mensagem')

        publish_request = attach_session_and_messages(
            self.factory.post(f'/itens/{assignment.id}/publicar/')
        )
        publish_request.user = self.teacher
        response = course_items.publish_course_item_view(publish_request, assignment.id)
        assignment.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertTrue(assignment.is_published)

        delete_message_request = attach_session_and_messages(
            self.factory.post(f'/forum/mensagens/{message.id}/excluir/')
        )
        delete_message_request.user = self.teacher
        response = course_items.delete_forum_message_view(delete_message_request, message.id)

        self.assertEqual(response.status_code, 302)
        self.assertFalse(ForumMessage.objects.filter(pk=message.id).exists())

        delete_forum_request = attach_session_and_messages(
            self.factory.post(f'/itens/{forum.id}/forum/excluir/')
        )
        delete_forum_request.user = self.teacher
        response = course_items.delete_forum_view(delete_forum_request, forum.id)

        self.assertEqual(response.status_code, 302)
        self.assertFalse(ForumItem.objects.filter(pk=forum.id).exists())
