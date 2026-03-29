from collections import defaultdict
from datetime import timedelta

from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Q
from django.middleware.csrf import get_token
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache

from .forms import SuperuserCreateUserForm
from .models import Activity, Enrollment, Submission, UserProfile


@never_cache
def login_view(request):
    if request.user.is_authenticated:
        return redirect('agora:index')

    context = {
        'active_form': 'login',
        'error_message': '',
        'initial_username': '',
        'initial_register_username': '',
        'initial_register_email': '',
        'csrf_token_value': get_token(request),
    }

    if request.method == 'POST':
        action = request.POST.get('action', 'login')

        if action == 'register':
            user_model = get_user_model()
            username = request.POST.get('register_username', '').strip()
            email = request.POST.get('register_email', '').strip()
            password = request.POST.get('register_password', '')
            password_confirm = request.POST.get('register_password_confirm', '')

            context['active_form'] = 'register'
            context['initial_register_username'] = username
            context['initial_register_email'] = email

            if not username or not password:
                context['error_message'] = 'Preencha usuário e senha para criar a conta.'
            elif password != password_confirm:
                context['error_message'] = 'As senhas informadas não coincidem.'
            elif user_model.objects.filter(username=username).exists():
                context['error_message'] = 'Esse nome de usuário já está em uso.'
            else:
                user = user_model.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                )
                login(request, user)
                return redirect('agora:index')
        else:
            username = request.POST.get('username', '').strip()
            password = request.POST.get('password', '')
            user = authenticate(request, username=username, password=password)

            context['initial_username'] = username

            if user is not None:
                login(request, user)
                return redirect('agora:index')

            context['error_message'] = 'Usuario ou senha invalidos.'

    return render(request, 'agora/login.html', context)


@never_cache
@login_required(login_url='agora:login')
def index(request):
    is_teacher = _is_teacher_user(request.user)
    user_role = UserProfile.Role.TEACHER if is_teacher else _get_user_role(request.user)

    if is_teacher:
        context = _build_teacher_dashboard_context(request.user)
    else:
        context = _build_student_dashboard_context(request.user)

    context['dashboard_kind'] = 'teacher' if is_teacher else 'student'
    context['user_role'] = 'Professor(a)' if is_teacher else 'Estudante'

    return render(request, 'agora/index.html', context)


def _build_student_dashboard_context(user):
    now = timezone.localtime()

    enrollments = list(
        Enrollment.objects.select_related('course', 'course__teacher')
        .filter(
            student=user,
            status=Enrollment.Status.ACTIVE,
        )
        .order_by('course__title')
    )

    course_ids = [enrollment.course_id for enrollment in enrollments]

    pending_activities_queryset = (
        Activity.objects.select_related('course')
        .filter(
            course_id__in=course_ids,
            is_published=True,
        )
        .exclude(
            submissions__student=user,
            submissions__status__in=[
                Submission.Status.SUBMITTED,
                Submission.Status.REVIEWED,
                Submission.Status.LATE,
            ],
        )
        .distinct()
    )

    pending_activities = sorted(
        pending_activities_queryset,
        key=lambda activity: (
            activity.due_date is None,
            activity.due_date or now,
            activity.title.lower(),
        ),
    )

    published_activity_totals = {
        item['course_id']: item['total']
        for item in Activity.objects.filter(course_id__in=course_ids, is_published=True)
        .values('course_id')
        .annotate(total=Count('id'))
    }

    completed_activity_totals = {
        item['activity__course_id']: item['total']
        for item in Submission.objects.filter(
            student=user,
            activity__course_id__in=course_ids,
            status__in=[
                Submission.Status.SUBMITTED,
                Submission.Status.REVIEWED,
                Submission.Status.LATE,
            ],
        )
        .values('activity__course_id')
        .annotate(total=Count('id'))
    }

    pending_by_course = defaultdict(list)
    overdue_activities = 0
    pending_cards = []

    for activity in pending_activities:
        due_date = timezone.localtime(activity.due_date) if activity.due_date else None
        is_overdue = bool(due_date and due_date < now)
        is_due_today = bool(due_date and due_date.date() == now.date())
        is_due_soon = bool(due_date and now.date() < due_date.date() <= (now + timedelta(days=3)).date())

        if is_overdue:
            status_label = 'Atrasada'
            status_tone = 'danger'
            overdue_activities += 1
        elif is_due_today:
            status_label = 'Vence hoje'
            status_tone = 'warning'
        elif is_due_soon:
            status_label = 'Próxima'
            status_tone = 'accent'
        else:
            status_label = 'Planejada' if due_date else 'Sem prazo'
            status_tone = 'neutral'

        item = {
            'id': activity.id,
            'title': activity.title,
            'course_title': activity.course.title,
            'course_code': activity.course.code,
            'activity_type': activity.get_activity_type_display(),
            'due_date': due_date,
            'due_label': due_date.strftime('%d/%m, %H:%M') if due_date else 'Sem data definida',
            'status_label': status_label,
            'status_tone': status_tone,
        }
        pending_cards.append(item)
        pending_by_course[activity.course_id].append(item)

    course_cards = []
    for index_number, enrollment in enumerate(enrollments):
        course = enrollment.course
        total_activities = published_activity_totals.get(course.id, 0)
        completed_activities = completed_activity_totals.get(course.id, 0)
        pending_count = len(pending_by_course[course.id])
        progress = int((completed_activities / total_activities) * 100) if total_activities else 0

        course_cards.append(
            {
                'id': course.id,
                'title': course.title,
                'code': course.code,
                'description': course.description,
                'teacher_name': course.teacher.get_full_name() or course.teacher.username,
                'pending_count': pending_count,
                'progress': progress,
                'accent': ['forest', 'sand', 'sage'][index_number % 3],
                'meta_label': f'{pending_count} pendente{"" if pending_count == 1 else "s"}',
            }
        )

    return {
        'course_cards': course_cards,
        'pending_cards': pending_cards[:5],
        'metrics': {
            'course_count': len(course_cards),
            'pending_count': len(pending_cards),
            'overdue_count': overdue_activities,
        },
        'page_title': 'Meus cursos e atividades a entregar.',
        'page_lead': 'Um painel simples, focado no que o aluno precisa acompanhar no dia a dia acadêmico.',
        'sidebar_title': 'Painel do aluno',
        'sidebar_summary': f'{len(pending_cards)} atividade{"s" if len(pending_cards) != 1 else ""} pendente{"s" if len(pending_cards) != 1 else ""}',
        'sidebar_helper': 'Priorize primeiro as entregas com prazo mais próximo e acompanhe seu progresso por disciplina.',
        'courses_heading': 'Meus cursos',
        'courses_eyebrow': 'Cursos matriculados',
        'courses_empty_title': 'Você ainda não possui cursos matriculados.',
        'courses_empty_text': 'Quando suas matriculas forem registradas, seus cursos aparecerão aqui com progresso e resumo das pendências.',
        'courses_summary': f'{len(course_cards)} em andamento · {overdue_activities} atrasada{"s" if overdue_activities != 1 else ""}',
        'work_heading': 'Atividades a entregar',
        'work_eyebrow': 'Pendências acadêmicas',
        'work_summary': f'{len(pending_cards)} abertas',
        'work_empty_title': 'Nenhuma atividade pendente agora.',
        'work_empty_text': 'Bom sinal: todas as atividades publicadas para seus cursos ativos já foram entregues ou ainda não existem pendências cadastradas.',
    }


def _build_teacher_dashboard_context(user):
    now = timezone.localtime()

    courses = list(
        user.courses_taught.all().order_by('title')
    )
    course_ids = [course.id for course in courses]

    student_counts = {
        item['course_id']: item['total']
        for item in Enrollment.objects.filter(
            course_id__in=course_ids,
            status=Enrollment.Status.ACTIVE,
        )
        .values('course_id')
        .annotate(total=Count('id'))
    }

    published_activity_totals = {
        item['course_id']: item['total']
        for item in Activity.objects.filter(course_id__in=course_ids, is_published=True)
        .values('course_id')
        .annotate(total=Count('id'))
    }

    activities_needing_review = list(
        Activity.objects.select_related('course')
        .filter(
            course__teacher=user,
            is_published=True,
            due_date__lt=now,
            submissions__status__in=[Submission.Status.SUBMITTED, Submission.Status.LATE],
        )
        .distinct()
        .order_by('due_date', 'title')
    )

    pending_review_counts = {
        item['activity_id']: item['total']
        for item in Submission.objects.filter(
            activity__course__teacher=user,
            activity__due_date__lt=now,
            status__in=[Submission.Status.SUBMITTED, Submission.Status.LATE],
        )
        .values('activity_id')
        .annotate(total=Count('id'))
    }

    reviewed_activity_totals = defaultdict(int)
    reviewed_activity_rows = (
        Submission.objects.filter(
            activity__course__teacher=user,
            activity__is_published=True,
        )
        .values('activity__course_id', 'activity_id')
        .annotate(
            total_submissions=Count('id'),
            pending_reviews=Count(
                'id',
                filter=Q(status__in=[Submission.Status.SUBMITTED, Submission.Status.LATE]),
            ),
        )
    )

    for row in reviewed_activity_rows:
        if row['total_submissions'] > 0 and row['pending_reviews'] == 0:
            reviewed_activity_totals[row['activity__course_id']] += 1

    review_count_by_course = defaultdict(int)
    review_cards = []
    review_count = 0

    for activity in activities_needing_review:
        course = activity.course
        due_date = timezone.localtime(activity.due_date) if activity.due_date else None
        pending_reviews = pending_review_counts.get(activity.id, 0)
        review_count_by_course[course.id] += 1
        review_count += 1

        review_cards.append(
            {
                'id': activity.id,
                'title': activity.title,
                'course_title': course.title,
                'course_code': course.code,
                'activity_type': activity.get_activity_type_display(),
                'due_label': due_date.strftime('%d/%m, %H:%M') if due_date else 'Sem data definida',
                'status_label': 'Correção pendente',
                'status_tone': 'danger',
                'review_volume': f'{pending_reviews} envio{"s" if pending_reviews != 1 else ""} aguardando avaliação',
            }
        )

    course_cards = []
    for index_number, course in enumerate(courses):
        total_activities = published_activity_totals.get(course.id, 0)
        student_total = student_counts.get(course.id, 0)
        review_total = review_count_by_course.get(course.id, 0)
        reviewed_total = reviewed_activity_totals.get(course.id, 0)
        progress = int((reviewed_total / total_activities) * 100) if total_activities else 0

        course_cards.append(
            {
                'id': course.id,
                'title': course.title,
                'code': course.code,
                'description': course.description,
                'teacher_name': course.teacher.get_full_name() or course.teacher.username,
                'pending_count': review_total,
                'progress': progress,
                'accent': ['forest', 'sand', 'sage'][index_number % 3],
                'meta_label': f'{student_total} aluno{"s" if student_total != 1 else ""} ativo{"s" if student_total != 1 else ""}',
                'progress_label': f'{reviewed_total}/{total_activities} atividades avaliadas',
            }
        )

    return {
        'course_cards': course_cards,
        'pending_cards': review_cards[:5],
        'metrics': {
            'course_count': len(course_cards),
            'pending_count': len(review_cards),
            'overdue_count': review_count,
        },
        'page_title': 'Cursos sob sua responsabilidade e atividades para corrigir.',
        'page_lead': 'Um painel para acompanhar suas turmas e identificar correções pendentes.',
        'sidebar_title': 'Painel do professor',
        'sidebar_summary': f'{len(review_cards)} atividade{"s" if len(review_cards) != 1 else ""} aguardando correção',
        'sidebar_helper': 'Acompanhe suas turmas ativas e priorize as atividades com prazo encerrado para manter o retorno aos estudantes em dia.',
        'courses_heading': 'Cursos que voce leciona',
        'courses_eyebrow': 'Turmas sob sua condução',
        'courses_empty_title': 'Você ainda nao possui cursos atribuidos para lecionar.',
        'courses_empty_text': 'Assim que um curso tiver você como professor responsável, ele aparecerá aqui com a fila de correções relacionada.',
        'courses_summary': f'{len(course_cards)} turma{"s" if len(course_cards) != 1 else ""} ativa{"s" if len(course_cards) != 1 else ""}',
        'work_heading': 'Atividades para corrigir',
        'work_eyebrow': 'Fila de correção',
        'work_summary': f'{len(review_cards)} atividade{"s" if len(review_cards) != 1 else ""} aguardando retorno',
        'work_empty_title': 'Nenhuma atividade vencida aguardando correção.',
        'work_empty_text': 'No momento, não há atividades com prazo encerrado esperando sua avaliação.',
    }


def _get_user_role(user):
    profile = getattr(user, 'profile', None)
    return getattr(profile, 'role', UserProfile.Role.STUDENT)


def _is_teacher_user(user):
    if _get_user_role(user) == UserProfile.Role.TEACHER:
        return True
    return user.courses_taught.exists()


@user_passes_test(lambda user: user.is_authenticated and user.is_superuser)
def create_user_view(request):
    form = SuperuserCreateUserForm(request.POST or None)
    created_user = None

    if request.method == 'POST' and form.is_valid():
        created_user = form.save()
        form = SuperuserCreateUserForm()

    return render(
        request,
        'agora/create_user.html',
        {
            'form': form,
            'created_user': created_user,
        },
    )


@never_cache
def logout_view(request):
    if request.method == 'POST':
        logout(request)

    return redirect('agora:index')
