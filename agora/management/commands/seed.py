from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from random import Random

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from agora.models import (
    Answer,
    AssignmentItem,
    Course,
    ForumMessage,
    ForumItem,
    Enrollment,
    Module,
    QuizItem,
    QuizOption,
    QuizQuestion,
    ResourceItem,
    Submission,
    UserProfile,
)

User = get_user_model()


DEMO_USERNAME_PREFIX = "demo_"
DEMO_COURSE_CODE_PREFIX = "DEMO-"


@dataclass(frozen=True)
class DemoUserSpec:
    username: str
    first_name: str
    last_name: str
    role: str
    performance: str = "mid"  # low | mid | high


class Command(BaseCommand):
    help = "Popula o banco com um dataset pequeno, verossímil e idempotente (bom para demo)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Remove apenas dados de demonstração (usuarios demo_* e cursos DEMO-*), e recria tudo.",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=1234,
            help="Semente para gerar pequenas variações reproduzíveis (default: 1234).",
        )
        parser.add_argument(
            "--password",
            default="demo123",
            help="Senha para todos os usuários de demonstração (default: demo123).",
        )

    def handle(self, *args, **options):
        reset: bool = options["reset"]
        seed: int = options["seed"]
        password: str = options["password"]

        rng = Random(seed)
        now = timezone.now()

        with transaction.atomic():
            if reset:
                self._reset_demo_data()

            result = self._seed_demo_data(rng=rng, now=now, password=password)

        self.stdout.write(self.style.SUCCESS("Seed finalizado."))
        self.stdout.write(result.summary)

    def _reset_demo_data(self) -> None:
        Course.objects.filter(code__startswith=DEMO_COURSE_CODE_PREFIX).delete()
        User.objects.filter(username__startswith=DEMO_USERNAME_PREFIX).delete()

    @dataclass(frozen=True)
    class _SeedResult:
        summary: str

    def _seed_demo_data(self, *, rng: Random, now, password: str) -> _SeedResult:
        users = self._ensure_demo_users(password=password)
        teacher_ana = users[f"{DEMO_USERNAME_PREFIX}prof_ana"]
        teacher_carlos = users[f"{DEMO_USERNAME_PREFIX}prof_carlos"]

        course_specs = [
            (
                f"{DEMO_COURSE_CODE_PREFIX}CS101",
                "Introdução à Programação",
                teacher_ana,
                60,
                "Lógica, variáveis, controle de fluxo, funções e testes básicos.",
            ),
            (
                f"{DEMO_COURSE_CODE_PREFIX}BD201",
                "Banco de Dados",
                teacher_carlos,
                80,
                "Modelagem, SQL, normalização, índices e transações.",
            ),
            (
                f"{DEMO_COURSE_CODE_PREFIX}AL203",
                "Algoritmos e Estruturas",
                teacher_ana,
                80,
                "Complexidade, estruturas clássicas, ordenação e busca.",
            ),
        ]

        courses: list[Course] = []
        for code, title, teacher, workload, syllabus in course_specs:
            course, created = Course.objects.get_or_create(
                code=code,
                defaults={
                    "title": title,
                    "description": "Curso de demonstração com dados fictícios para testes visuais e apresentações.",
                    "syllabus": syllabus,
                    "workload_hours": workload,
                    "teacher": teacher,
                    "is_published": True,
                }
            )
            if not created:
                updates = {}
                if course.title != title:
                    updates["title"] = title
                if course.teacher_id != teacher.id:
                    updates["teacher"] = teacher
                if course.workload_hours != workload:
                    updates["workload_hours"] = workload
                if course.syllabus != syllabus:
                    updates["syllabus"] = syllabus
                if not course.is_published:
                    updates["is_published"] = True
                if updates:
                    for k, v in updates.items():
                        setattr(course, k, v)
                    course.save(update_fields=list(updates.keys()))

            courses.append(course)

        students = [
            users[f"{DEMO_USERNAME_PREFIX}aluno_joao"],
            users[f"{DEMO_USERNAME_PREFIX}aluna_maria"],
            users[f"{DEMO_USERNAME_PREFIX}aluno_pedro"],
            users[f"{DEMO_USERNAME_PREFIX}aluna_luiza"],
            users[f"{DEMO_USERNAME_PREFIX}aluno_rodrigo"],
            users[f"{DEMO_USERNAME_PREFIX}aluna_camila"],
            users[f"{DEMO_USERNAME_PREFIX}aluno_felipe"],
            users[f"{DEMO_USERNAME_PREFIX}aluna_bruna"],
            users[f"{DEMO_USERNAME_PREFIX}aluno_igor"],
        ]

        # Matrículas: 4–5 alunos por curso, com sobreposição parcial.
        enrollment_matrix = {
            f"{DEMO_COURSE_CODE_PREFIX}CS101": ["joao", "maria", "pedro", "luiza", "igor"],
            f"{DEMO_COURSE_CODE_PREFIX}BD201": ["maria", "rodrigo", "camila", "felipe"],
            f"{DEMO_COURSE_CODE_PREFIX}AL203": ["joao", "bruna", "felipe", "igor", "pedro"],
        }

        student_by_short = {u.username.split(f"{DEMO_USERNAME_PREFIX}", 1)[1].split("_")[-1]: u for u in students}

        for course in courses:
            short_list = enrollment_matrix.get(course.code, [])
            for short in short_list:
                student = student_by_short[short]
                status = Enrollment.Status.ACTIVE
                final_grade = None

                # Um caso de conclusão e um de cancelamento.
                if course.code.endswith("CS101") and short == "joao":
                    status = Enrollment.Status.COMPLETED
                    final_grade = Decimal("88.00")
                if course.code.endswith("AL203") and short == "pedro":
                    status = Enrollment.Status.CANCELLED
                    final_grade = None

                enrollment, created = Enrollment.objects.get_or_create(
                    student=student,
                    course=course,
                    defaults={"status": status, "final_grade": final_grade},
                )
                if not created:
                    updates = {}
                    if enrollment.status != status:
                        updates["status"] = status
                    if enrollment.final_grade != final_grade:
                        updates["final_grade"] = final_grade
                    if updates:
                        for k, v in updates.items():
                            setattr(enrollment, k, v)
                        enrollment.save(update_fields=list(updates.keys()))

        module_titles = ("Boas-vindas", "Conteúdo", "Avaliações")
        for course in courses:
            modules: list[Module] = []
            for order, title in enumerate(module_titles, start=1):
                module, created = Module.objects.get_or_create(
                    course=course,
                    order=order,
                    defaults={"title": title, "description": f"Módulo {order}: {title}"},
                )
                if not created:
                    updates = {}
                    if module.title != title:
                        updates["title"] = title
                    if updates:
                        for k, v in updates.items():
                            setattr(module, k, v)
                        module.save(update_fields=list(updates.keys()))
                modules.append(module)

            self._seed_resources(course=course, modules=modules, rng=rng)
            assignments = self._seed_assignments(course=course, modules=modules, now=now, rng=rng)
            quiz = self._seed_quiz(course=course, modules=modules, now=now, rng=rng)
            forum = self._seed_forum(course=course, modules=modules, now=now)

            enrolled = Enrollment.objects.filter(
                course=course,
                status__in=[Enrollment.Status.ACTIVE, Enrollment.Status.COMPLETED],
            ).select_related("student")
            enrolled_students = [e.student for e in enrolled]

            self._seed_submissions(
                course=course,
                assignments=assignments,
                students=enrolled_students,
                now=now,
                rng=rng,
            )
            self._seed_quiz_answers(quiz=quiz, students=enrolled_students, rng=rng)
            self._seed_forum_messages(forum=forum, students=enrolled_students, now=now, rng=rng)

        summary = self._build_summary()
        return self._SeedResult(summary=summary)

    def _seed_resources(self, *, course: Course, modules: list[Module], rng: Random) -> None:
        per_module = [
            [
                ("Plano de ensino e cronograma", "https://example.com/plano-e-cronograma.pdf"),
                ("Como estudar na plataforma", "https://example.com/guia-plataforma.pdf"),
            ],
            [
                ("Slides — conceitos essenciais", "https://example.com/slides-conceitos.pdf"),
            ],
            [
                ("Rubrica de avaliação", "https://example.com/rubrica.pdf"),
            ],
        ]

        for module, resources in zip(modules, per_module, strict=False):
            for title, url in resources:
                ResourceItem.objects.get_or_create(
                    course=course,
                    title=f"{title} ({course.code})",
                    defaults={
                        "module": module,
                        "description": rng.choice(
                            [
                                "Material de apoio para acompanhar as atividades.",
                                "Recurso recomendado para preparar as entregas.",
                                "Leitura curta para fixar os conceitos principais.",
                            ]
                        ),
                        "attachment_url": url,
                        "is_published": True,
                        "created_by": course.teacher,
                    },
                )

    def _seed_assignments(self, *, course: Course, modules: list[Module], now, rng: Random) -> list[AssignmentItem]:
        titles = [
            "Implementação incremental com testes",
            "Consulta e modelagem: do ER ao SQL",
            "Análise de complexidade e trade-offs",
            "Refatoração guiada por casos de teste",
        ]
        prompts = [
            "Entregue uma solução com passos claros e justificativas curtas.",
            "Inclua exemplos e explique decisões de projeto.",
            "Pense em casos de borda e escreva testes mínimos.",
        ]

        past_due = now - timedelta(days=6, hours=3)
        future_due = now + timedelta(days=5, hours=2)

        past_title = rng.choice(titles)
        past, _ = AssignmentItem.objects.get_or_create(
            course=course,
            title=f"{past_title} ({course.code})",
            defaults={
                "module": modules[2],
                "description": rng.choice(prompts),
                "due_date": past_due,
                "max_score": Decimal("10.00"),
                "statement_url": "https://example.com/enunciado-tarefa.pdf",
                "is_published": True,
                "created_by": course.teacher,
            },
        )

        future_title_candidates = [t for t in titles if t != past_title] or titles
        future, _ = AssignmentItem.objects.get_or_create(
            course=course,
            title=f"{rng.choice(future_title_candidates)} ({course.code})",
            defaults={
                "module": modules[2],
                "description": rng.choice(prompts),
                "due_date": future_due,
                "max_score": Decimal("15.00"),
                "statement_url": "https://example.com/enunciado-tarefa-2.pdf",
                "is_published": True,
                "created_by": course.teacher,
            },
        )
        return [past, future]

    def _seed_quiz(self, *, course: Course, modules: list[Module], now, rng: Random) -> QuizItem:
        quiz, _ = QuizItem.objects.get_or_create(
            course=course,
            title=f"Quiz — revisão semanal ({course.code})",
            defaults={
                "module": modules[2],
                "description": "Quiz curto para revisar conceitos e identificar dúvidas.",
                "due_date": now + timedelta(days=2, hours=1),
                "max_score": Decimal("20.00"),
                "allow_resubmissions": True,
                "is_published": True,
                "created_by": course.teacher,
            },
        )

        if not quiz.questions.exists():
            questions = [
                (
                    "Qual opção melhor representa a ideia principal do tópico desta semana?",
                    QuizQuestion.QuestionType.SINGLE_CHOICE,
                    ["Apenas memorizar definições.", "Aplicar o conceito em exemplos.", "Ignorar casos de borda.", "Evitar testes."],
                    2,
                ),
                (
                    "Selecione as alternativas que ajudam a tornar uma solução mais robusta.",
                    QuizQuestion.QuestionType.MULTIPLE_CHOICE,
                    ["Escrever testes para casos de borda.", "Documentar decisões.", "Depender de comportamento indefinido.", "Validar entradas."],
                    {1, 2, 4},
                ),
            ]
            for order, (statement, qtype, options, correct) in enumerate(questions, start=1):
                question = QuizQuestion.objects.create(
                    quiz=quiz,
                    statement=statement,
                    question_type=qtype,
                    order=order,
                    weight=Decimal("1.00"),
                )
                for o_order, text in enumerate(options, start=1):
                    is_correct = o_order == correct if isinstance(correct, int) else o_order in correct
                    QuizOption.objects.create(
                        question=question,
                        text=text,
                        order=o_order,
                        is_correct=is_correct,
                    )

        return quiz

    def _seed_forum(self, *, course: Course, modules: list[Module], now) -> ForumItem:
        forum, _ = ForumItem.objects.get_or_create(
            course=course,
            title=f"Fórum — dúvidas gerais ({course.code})",
            defaults={
                "module": modules[1],
                "description": "Espaço para tirar dúvidas, compartilhar links e combinar estudos.",
                "is_published": True,
                "created_by": course.teacher,
            },
        )
        return forum

    def _seed_submissions(self, *, course: Course, assignments: list[AssignmentItem], students: list[User], now, rng: Random) -> None:
        if not students:
            return

        feedback_bank = [
            "Boa solução. Sugestão: melhore a organização do código e adicione testes.",
            "Caminho correto, mas faltaram casos de borda.",
            "Bem escrito e claro. Parabéns pelo capricho nos testes.",
        ]

        # Para a tarefa passada: 2–3 entregas com variedade.
        past = assignments[0]
        past_students = rng.sample(students, k=min(len(students), rng.choice([2, 3])))
        if past_students:
            reviewed = past_students[0]
            Submission.objects.get_or_create(
                assignment=past,
                student=reviewed,
                defaults={
                    "content": "Entrega completa com explicações e exemplos.",
                    "status": Submission.Status.REVIEWED,
                    "submitted_at": now - timedelta(days=5, hours=2),
                    "score": Decimal("9.00"),
                    "feedback": rng.choice(feedback_bank),
                    "graded_by": past.created_by,
                    "graded_at": now - timedelta(days=4, hours=18),
                },
            )
        if len(past_students) >= 2:
            late = past_students[1]
            Submission.objects.get_or_create(
                assignment=past,
                student=late,
                defaults={
                    "content": "Entrega com pequenas inconsistências, mas resolvendo o essencial.",
                    "status": Submission.Status.LATE,
                    "submitted_at": now - timedelta(days=4, hours=3),
                },
            )
        if len(past_students) >= 3:
            draft = past_students[2]
            Submission.objects.get_or_create(
                assignment=past,
                student=draft,
                defaults={
                    "content": "Rascunho inicial; faltam testes e revisão final.",
                    "status": Submission.Status.DRAFT,
                },
            )

        # Para a tarefa futura: 2 entregas (um rascunho e uma submissão).
        future = assignments[1]
        future_students = rng.sample(students, k=min(len(students), 2))
        if future_students:
            Submission.objects.get_or_create(
                assignment=future,
                student=future_students[0],
                defaults={
                    "content": "Rascunho com a estrutura do trabalho e alguns casos de teste.",
                    "status": Submission.Status.DRAFT,
                },
            )
        if len(future_students) >= 2:
            Submission.objects.get_or_create(
                assignment=future,
                student=future_students[1],
                defaults={
                    "content": "Entrega parcial; faltam otimizações e revisão do texto.",
                    "status": Submission.Status.SUBMITTED,
                    "submitted_at": now - timedelta(hours=8),
                },
            )

    def _seed_quiz_answers(self, *, quiz: QuizItem, students: list[User], rng: Random) -> None:
        if not students:
            return

        perf_by_username = self._demo_performance_by_username()

        for student in students:
            if Answer.objects.filter(quiz=quiz, student=student).exists():
                continue

            performance = perf_by_username.get(student.username, "mid")
            for question in quiz.questions.all():
                options = list(question.options.order_by("order"))
                if not options:
                    continue

                if question.question_type == QuizQuestion.QuestionType.SINGLE_CHOICE:
                    correct_options = [o for o in options if o.is_correct]
                    wrong_options = [o for o in options if not o.is_correct]
                    if performance == "high":
                        chosen = rng.choice(correct_options or options)
                    elif performance == "low":
                        chosen = rng.choice(wrong_options or options)
                    else:
                        chosen = rng.choice((correct_options if rng.random() < 0.6 else wrong_options) or options)

                    Answer.objects.create(
                        quiz=quiz,
                        question=question,
                        selected_option=chosen,
                        student=student,
                    )
                else:
                    # MULTIPLE_CHOICE: seleciona 2 opções (pode incluir erro em perfis mais baixos).
                    correct = [o for o in options if o.is_correct]
                    wrong = [o for o in options if not o.is_correct]
                    chosen = []
                    if performance == "high":
                        chosen = (correct[:2] if len(correct) >= 2 else correct) or options[:2]
                    elif performance == "low":
                        chosen = (wrong[:2] if len(wrong) >= 2 else wrong) or options[:2]
                    else:
                        chosen = []
                        if correct:
                            chosen.append(correct[0])
                        if wrong:
                            chosen.append(wrong[0])
                        if len(chosen) < 2:
                            chosen = options[:2]

                    for opt in chosen:
                        Answer.objects.create(
                            quiz=quiz,
                            question=question,
                            selected_option=opt,
                            student=student,
                        )

    def _seed_forum_messages(self, *, forum: ForumItem, students: list[User], now, rng: Random) -> None:
        if forum.messages.exists():
            return
        if not students:
            return

        teacher = forum.created_by
        root = ForumMessage.objects.create(
            forum=forum,
            author=teacher,
            content="Bem-vindos! Se tiverem dúvidas, postem aqui com o máximo de contexto possível.",
        )

        replies = [
            ("Tenho dificuldade em entender a diferença entre exemplos e casos de teste. Alguma dica?", "low"),
            ("Vale a pena começar pela modelagem antes de codar? Em que situações?", "mid"),
            ("Compartilhei um link de referência no material do módulo. Recomendo!", "high"),
        ]
        perf_by_username = self._demo_performance_by_username()

        picked = rng.sample(students, k=min(len(students), rng.choice([2, 3, 4])))
        created = []
        for student in picked:
            content, _ = rng.choice(replies)
            created.append(
                ForumMessage.objects.create(
                    forum=forum,
                    author=student,
                    parent=root,
                    content=content,
                )
            )

        # Uma resposta encadeada de aluno para aluno.
        if len(created) >= 2:
            ForumMessage.objects.create(
                forum=forum,
                author=rng.choice(students),
                parent=created[0],
                content="Boa pergunta. O que me ajudou foi começar com um exemplo pequeno e depois escrever os testes.",
            )

        # Professor fecha com uma orientação.
        ForumMessage.objects.create(
            forum=forum,
            author=teacher,
            parent=root,
            content="Dica geral: comece pequeno, valide com testes e evolua em passos. Tragam exemplos de entradas/saídas.",
        )

        # Ajusta timestamps para parecer “ao longo do dia”.
        for idx, msg in enumerate(forum.messages.order_by("id")):
            msg.created_at = now - timedelta(hours=10 - idx * 2)
            msg.updated_at = msg.created_at
            msg.save(update_fields=["created_at", "updated_at"])

    def _ensure_demo_users(self, *, password: str) -> dict[str, User]:
        specs = [
            DemoUserSpec(
                username=f"{DEMO_USERNAME_PREFIX}prof_ana",
                first_name="Ana",
                last_name="Souza",
                role=UserProfile.Role.TEACHER,
            ),
            DemoUserSpec(
                username=f"{DEMO_USERNAME_PREFIX}prof_carlos",
                first_name="Carlos",
                last_name="Silva",
                role=UserProfile.Role.TEACHER,
            ),
            DemoUserSpec(
                username=f"{DEMO_USERNAME_PREFIX}aluno_joao",
                first_name="João",
                last_name="Pereira",
                role=UserProfile.Role.STUDENT,
                performance="high",
            ),
            DemoUserSpec(
                username=f"{DEMO_USERNAME_PREFIX}aluna_maria",
                first_name="Maria",
                last_name="Oliveira",
                role=UserProfile.Role.STUDENT,
                performance="mid",
            ),
            DemoUserSpec(
                username=f"{DEMO_USERNAME_PREFIX}aluno_pedro",
                first_name="Pedro",
                last_name="Santos",
                role=UserProfile.Role.STUDENT,
                performance="low",
            ),
            DemoUserSpec(
                username=f"{DEMO_USERNAME_PREFIX}aluna_luiza",
                first_name="Luiza",
                last_name="Almeida",
                role=UserProfile.Role.STUDENT,
                performance="mid",
            ),
            DemoUserSpec(
                username=f"{DEMO_USERNAME_PREFIX}aluno_rodrigo",
                first_name="Rodrigo",
                last_name="Costa",
                role=UserProfile.Role.STUDENT,
                performance="mid",
            ),
            DemoUserSpec(
                username=f"{DEMO_USERNAME_PREFIX}aluna_camila",
                first_name="Camila",
                last_name="Barros",
                role=UserProfile.Role.STUDENT,
                performance="low",
            ),
            DemoUserSpec(
                username=f"{DEMO_USERNAME_PREFIX}aluno_felipe",
                first_name="Felipe",
                last_name="Lima",
                role=UserProfile.Role.STUDENT,
                performance="high",
            ),
            DemoUserSpec(
                username=f"{DEMO_USERNAME_PREFIX}aluna_bruna",
                first_name="Bruna",
                last_name="Ramos",
                role=UserProfile.Role.STUDENT,
                performance="mid",
            ),
            DemoUserSpec(
                username=f"{DEMO_USERNAME_PREFIX}aluno_igor",
                first_name="Igor",
                last_name="Mendes",
                role=UserProfile.Role.STUDENT,
                performance="high",
            ),
        ]

        users: dict[str, User] = {}
        for spec in specs:
            user, created = User.objects.get_or_create(
                username=spec.username,
                defaults={"first_name": spec.first_name, "last_name": spec.last_name},
            )

            update_fields = []
            if not created:
                for field, value in (("first_name", spec.first_name), ("last_name", spec.last_name)):
                    if getattr(user, field) != value:
                        setattr(user, field, value)
                        update_fields.append(field)

            user.set_password(password)
            update_fields.append("password")
            user.save(update_fields=list(dict.fromkeys(update_fields)))

            profile = getattr(user, "profile", None)
            if profile is None:
                profile = UserProfile.objects.create(user=user)
            if profile.role != spec.role:
                profile.role = spec.role
            profile.ensure_academic_id(user.date_joined)
            profile.save()

            users[user.username] = user

        return users

    def _demo_performance_by_username(self) -> dict[str, str]:
        # Fonte única para coerência (quiz/fórum) sem depender do modelo.
        return {
            f"{DEMO_USERNAME_PREFIX}aluno_joao": "high",
            f"{DEMO_USERNAME_PREFIX}aluna_maria": "mid",
            f"{DEMO_USERNAME_PREFIX}aluno_pedro": "low",
            f"{DEMO_USERNAME_PREFIX}aluna_luiza": "mid",
            f"{DEMO_USERNAME_PREFIX}aluno_rodrigo": "mid",
            f"{DEMO_USERNAME_PREFIX}aluna_camila": "low",
            f"{DEMO_USERNAME_PREFIX}aluno_felipe": "high",
            f"{DEMO_USERNAME_PREFIX}aluna_bruna": "mid",
            f"{DEMO_USERNAME_PREFIX}aluno_igor": "high",
        }

    def _build_summary(self) -> str:
        demo_users = User.objects.filter(username__startswith=DEMO_USERNAME_PREFIX)
        demo_courses = Course.objects.filter(code__startswith=DEMO_COURSE_CODE_PREFIX)
        demo_enrollments = Enrollment.objects.filter(course__in=demo_courses)
        demo_assignments = AssignmentItem.objects.filter(course__in=demo_courses)
        demo_quizzes = QuizItem.objects.filter(course__in=demo_courses)
        demo_forums = ForumItem.objects.filter(course__in=demo_courses)
        demo_submissions = Submission.objects.filter(assignment__in=demo_assignments)
        demo_answers = Answer.objects.filter(quiz__in=demo_quizzes)
        demo_messages = ForumMessage.objects.filter(forum__in=demo_forums)

        return (
            "Resumo demo:\n"
            f"- Usuários: {demo_users.count()}\n"
            f"- Cursos: {demo_courses.count()}\n"
            f"- Matrículas: {demo_enrollments.count()}\n"
            f"- Tarefas: {demo_assignments.count()} · Entregas: {demo_submissions.count()}\n"
            f"- Quizzes: {demo_quizzes.count()} · Respostas: {demo_answers.count()}\n"
            f"- Fóruns: {demo_forums.count()} · Mensagens: {demo_messages.count()}"
        )
