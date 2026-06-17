from random import Random

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from agora.management.commands.seed import Command
from agora.models import (
    Answer,
    AssignmentItem,
    Course,
    Enrollment,
    ForumItem,
    ForumMessage,
    Module,
    QuizItem,
    QuizQuestion,
    Submission,
    UserProfile,
)


class SeedCommandHelperTests(TestCase):
    def setUp(self):
        self.command = Command()
        self.password = 'demo123'
        self.users = self.command._ensure_demo_users(password=self.password)
        self.teacher = self.users['demo_prof_ana']
        self.students = [
            self.users['demo_aluno_joao'],
            self.users['demo_aluna_maria'],
            self.users['demo_aluno_pedro'],
        ]
        self.course = Course.objects.create(
            code='DEMO-TST',
            title='Curso Demo Teste',
            description='Curso para testes.',
            syllabus='Teste',
            workload_hours=40,
            teacher=self.teacher,
            is_published=True,
        )
        self.modules = [
            Module.objects.create(course=self.course, title='Boas-vindas', order=1),
            Module.objects.create(course=self.course, title='Conteudo', order=2),
            Module.objects.create(course=self.course, title='Avaliacoes', order=3),
        ]

    def test_ensure_demo_users_creates_roles_and_reuses_existing_names(self):
        self.assertEqual(len(self.users), 11)
        self.assertEqual(self.teacher.profile.role, UserProfile.Role.TEACHER)
        self.assertEqual(self.users['demo_aluno_joao'].profile.role, UserProfile.Role.STUDENT)
        self.assertTrue(self.users['demo_aluno_joao'].profile.academic_id)

        self.teacher.first_name = 'Nome antigo'
        self.teacher.save(update_fields=['first_name'])
        users = self.command._ensure_demo_users(password=self.password)

        self.assertEqual(users['demo_prof_ana'].first_name, 'Ana')

    def test_seed_quiz_and_answers_are_idempotent(self):
        quiz = self.command._seed_quiz(
            course=self.course,
            modules=self.modules,
            now=timezone.now(),
            rng=Random(7),
        )
        self.command._seed_quiz(
            course=self.course,
            modules=self.modules,
            now=timezone.now(),
            rng=Random(7),
        )

        self.assertEqual(quiz.questions.count(), 2)
        self.assertEqual(QuizQuestion.objects.filter(quiz=quiz).count(), 2)

        self.command._seed_quiz_answers(quiz=quiz, students=self.students, rng=Random(7))
        first_answer_count = Answer.objects.filter(quiz=quiz).count()
        self.command._seed_quiz_answers(quiz=quiz, students=self.students, rng=Random(7))

        self.assertGreater(first_answer_count, 0)
        self.assertEqual(Answer.objects.filter(quiz=quiz).count(), first_answer_count)

    def test_seed_assignments_and_submissions_create_varied_statuses(self):
        assignments = self.command._seed_assignments(
            course=self.course,
            modules=self.modules,
            now=timezone.now(),
            rng=Random(5),
        )

        self.assertEqual(len(assignments), 2)

        self.command._seed_submissions(
            course=self.course,
            assignments=assignments,
            students=self.students,
            now=timezone.now(),
            rng=Random(5),
        )

        statuses = set(
            Submission.objects.filter(assignment__in=assignments).values_list('status', flat=True)
        )
        self.assertIn(Submission.Status.REVIEWED, statuses)
        self.assertTrue(
            statuses.intersection(
                {Submission.Status.LATE, Submission.Status.DRAFT, Submission.Status.SUBMITTED}
            )
        )

    def test_seed_forum_messages_creates_thread_and_is_idempotent(self):
        forum = self.command._seed_forum(
            course=self.course,
            modules=self.modules,
            now=timezone.now(),
        )

        self.command._seed_forum_messages(
            forum=forum,
            students=self.students,
            now=timezone.now(),
            rng=Random(9),
        )
        first_count = ForumMessage.objects.filter(forum=forum).count()
        self.command._seed_forum_messages(
            forum=forum,
            students=self.students,
            now=timezone.now(),
            rng=Random(9),
        )

        self.assertGreaterEqual(first_count, 4)
        self.assertEqual(ForumMessage.objects.filter(forum=forum).count(), first_count)
        self.assertTrue(ForumMessage.objects.filter(forum=forum, parent__isnull=False).exists())

    def test_build_summary_counts_seeded_demo_objects(self):
        call_command('seed', '--reset', '--seed', '11', '--password', self.password)

        summary = self.command._build_summary()

        self.assertIn('Resumo demo:', summary)
        self.assertIn('- Usuários: 11', summary)
        self.assertIn('- Cursos: 3', summary)
        self.assertIn('- Tarefas:', summary)
        self.assertIn('- Quizzes:', summary)
        self.assertIn('- Fóruns:', summary)
