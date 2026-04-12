from collections import defaultdict

import locale
locale.setlocale(locale.LC_TIME, 'pt_BR.UTF-8')
import calendar as month_calendar
from datetime import date
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache

from .forms import ActivityCreateForm, CourseCreateForm, ModuleCreateForm, SuperuserCreateUserForm
from .models import Activity, Course, Enrollment, Module, Submission, UserProfile


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

            context['error_message'] = 'Usuário ou senha inválidos.'

    return render(request, 'agora/login.html', context)


@never_cache
@login_required(login_url='agora:login')
def index(request):
    role = _user_role(request.user)

    if role == UserProfile.Role.TEACHER:
        context = _build_teacher_dashboard_context(request.user)
    else:
        context = _build_student_dashboard_context(request.user)

    course_cards = context.pop('course_cards')
    pending_cards = context.pop('pending_cards')

    context['courses_page'] = Paginator(course_cards, 6).get_page(request.GET.get('courses_page'))
    context['work_page'] = Paginator(pending_cards, 5).get_page(request.GET.get('work_page'))

    return render(request, 'agora/index.html', context)


def _user_role(user):
    profile = getattr(user, 'profile', None)
    return getattr(profile, 'role', UserProfile.Role.STUDENT)


def _build_teacher_dashboard_context(user):
    now = timezone.localtime()

    courses = list(user.courses_taught.all().order_by('title'))
    course_ids = [course.id for course in courses]

    course_student_counts = {
        item['course_id']: item['total']
        for item in Enrollment.objects.filter(
            course_id__in=course_ids,
            status=Enrollment.Status.ACTIVE,
        )
        .values('course_id')
        .annotate(total=Count('id'))
    }

    course_published_activities = {
        item['course_id']: item['total']
        for item in Activity.objects.filter(course_id__in=course_ids, is_published=True)
        .values('course_id')
        .annotate(total=Count('id'))
    }

    activities_pending_review = list(
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
            activity__is_published=True,
            activity__due_date__lt=now,
            status__in=[Submission.Status.SUBMITTED, Submission.Status.LATE],
        )
        .values('activity_id')
        .annotate(total=Count('id'))
    }

    pending_count_by_course = defaultdict(int)
    pending_cards = []

    for activity in activities_pending_review:
        course = activity.course
        pending_reviews = pending_review_counts.get(activity.id, 0)

        pending_count_by_course[course.id] += 1

        pending_cards.append({
                'id': activity.id,
                'title': activity.title,
                'course_title': course.title,
                'course_code': course.code,
                'activity_type': activity.get_activity_type_display(),
                'status_label': 'Correção pendente',
                'status_tone': 'danger',
                'meta_label': f'{pending_reviews} envio{"s" if pending_reviews != 1 else ""} aguardando avaliação',
            }
        )

    course_cards = []
    for index_number, course in enumerate(courses):
        total_activities = course_published_activities.get(course.id, 0)
        total_students = course_student_counts.get(course.id, 0)
        pending = pending_count_by_course.get(course.id, 0)
        progress = int((1 - pending / total_activities) * 100) if total_activities else 0

        course_cards.append({
                'id': course.id,
                'title': course.title,
                'code': course.code,
                'progress': progress,
                'accent': ['forest', 'sand', 'sage'][index_number % 3],
                'meta_label': f'{total_students} aluno{"s" if total_students != 1 else ""} ativo{"s" if total_students != 1 else ""}',
                'progress_label': f'{total_activities - pending}/{total_activities} atividades avaliadas',
            }
        )

    return {
        'course_cards': course_cards,
        'pending_cards': pending_cards,
        'courses_count': len(course_cards),
        'pending_count': len(pending_cards),
    }


def _build_student_dashboard_context(user):
    now = timezone.localtime()

    enrollments = list(user.enrollments.filter(
        status=Enrollment.Status.ACTIVE
    ).select_related('course').order_by('course__title'))

    course_ids = [enrollment.course_id for enrollment in enrollments]

    course_published_activities = {
        item['course_id']: item['total']
        for item in Activity.objects.filter(course_id__in=course_ids, is_published=True)
        .values('course_id')
        .annotate(total=Count('id'))
    }

    activities_pending_submission = list(
        Activity.objects.select_related('course')
        .filter(
            course_id__in=course_ids,
            is_published=True
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
        .order_by('due_date', 'title')
    )

    pending_count_by_course = defaultdict(int)
    pending_cards = []

    overdue_activities = 0

    for activity in activities_pending_submission:
        due_date = timezone.localtime(activity.due_date) if activity.due_date else None
        is_overdue = bool(due_date and due_date < now)
        is_due_today = bool(due_date and due_date.date() == now.date())
        is_due_soon = bool(due_date and now.date() < due_date.date() <= (now + timedelta(days=3)).date())
    
        pending_count_by_course[activity.course_id] += 1

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

        pending_cards.append({
            'id': activity.id,
            'title': activity.title,
            'course_title': activity.course.title,
            'course_code': activity.course.code,
            'activity_type': activity.get_activity_type_display(),
            'status_label': status_label,
            'status_tone': status_tone,
            'meta_label': f'Prazo de entrega: {due_date.strftime('%d/%m, %H:%M') if due_date else "Sem data definida" }'
        })

    course_cards = []
    for index_number, enrollment in enumerate(enrollments):
        course = enrollment.course
        total_activities = course_published_activities.get(course.id, 0)
        pending = pending_count_by_course.get(course.id, 0)
        progress = int((1 - pending / total_activities) * 100) if total_activities else 0

        course_cards.append({
                'id': course.id,
                'title': course.title,
                'code': course.code,
                'progress': progress,
                'accent': ['forest', 'sand', 'sage'][index_number % 3],
                'meta_label': f'Professor(a): {course.teacher.get_full_name() or course.teacher.username}',
                'progress_label': f'{pending} atividade{"" if pending == 1 else "s"} pendente{"" if pending == 1 else "s"}'
        })

    return {
        'course_cards': course_cards,
        'pending_cards': pending_cards,
        'courses_count': len(course_cards),
        'pending_count': len(pending_cards),
        'overdue_activities': overdue_activities,
    }


@never_cache
@login_required(login_url='agora:login')
def courses_hub_view(request):
    role = _user_role(request.user)

    if role == UserProfile.Role.TEACHER:
        form = CourseCreateForm(request.POST or None)
        if request.method == 'POST' and request.POST.get('action') == 'create_course' and form.is_valid():
            course = form.save(commit=False)
            course.teacher = request.user
            course.full_clean()
            course.save()
            messages.success(request, f'O curso {course.code} foi criado com sucesso.')
            return redirect('agora:courses_hub')

        taught_courses = list(
            request.user.courses_taught.all().order_by('title')
        )
        active_student_counts = {
            item['course_id']: item['total']
            for item in Enrollment.objects.filter(
                course__teacher=request.user,
                status=Enrollment.Status.ACTIVE,
            )
            .values('course_id')
            .annotate(total=Count('id'))
        }
        pending_requests = list(
            Enrollment.objects.select_related('student', 'course')
            .filter(
                course__teacher=request.user,
                status=Enrollment.Status.PENDING,
            )
            .order_by('course__title', 'student__username')
        )

        taught_course_cards = [
            {
                'id': course.id, # Added course ID for linking to course_detail_view
                'code': course.code,
                'title': course.title,
                'description': course.description,
                'is_published': course.is_published,
                'active_students': active_student_counts.get(course.id, 0),
                'workload_hours': course.workload_hours,
            }
            for course in taught_courses
        ]

        context = {
            'form': form,
            'taught_courses_page': Paginator(taught_course_cards, 3).get_page(request.GET.get('taught_courses_page')),
            'pending_requests_page': Paginator(pending_requests, 5).get_page(request.GET.get('pending_requests_page')),
            'taught_courses_count': len(taught_course_cards),
            'pending_requests_count': len(pending_requests),
        }
        return render(request, 'agora/courses_hub.html', context)

    published_courses = list(
        Course.objects.select_related('teacher')
        .filter(is_published=True)
        .order_by('title')
    )
    existing_enrollments = {
        enrollment.course_id: enrollment
        for enrollment in Enrollment.objects.select_related('course', 'course__teacher').filter(
            student=request.user,
            course__is_published=True,
        )
    }

    available_courses = []
    for course in published_courses:
        enrollment = existing_enrollments.get(course.id)

        if enrollment and enrollment.status == Enrollment.Status.ACTIVE:
            continue

        request_label = 'Solicitar matrícula'
        request_disabled = False
        status_badge = None
        helper_text = None

        if enrollment and enrollment.status == Enrollment.Status.PENDING:
            request_label = 'Solicitação enviada'
            request_disabled = True
            status_badge = 'Aguardando aprovação'
            helper_text = 'Seu pedido já foi enviado e está aguardando resposta do professor.'
        elif enrollment and enrollment.status == Enrollment.Status.COMPLETED:
            request_label = 'Curso concluído'
            request_disabled = True
            status_badge = 'Concluído'
            helper_text = 'Esse curso já aparece no seu histórico e não precisa de uma nova solicitação.'
        elif enrollment and enrollment.status == Enrollment.Status.CANCELLED:
            status_badge = 'Solicitação anterior recusada'
            helper_text = 'Você pode enviar uma nova solicitação de matrícula para este curso.'

        available_courses.append(
            {
                'id': course.id,
                'code': course.code,
                'title': course.title,
                'description': course.description,
                'teacher_name': course.teacher.get_full_name() or course.teacher.username,
                'workload_hours': course.workload_hours,
                'request_label': request_label,
                'request_disabled': request_disabled,
                'status_badge': status_badge,
                'helper_text': helper_text,
            }
        )

    context = {
        'available_courses_page': Paginator(available_courses, 3).get_page(request.GET.get('available_courses_page')),
        'available_courses_count': len(available_courses),
    }
    return render(request, 'agora/courses_hub.html', context)


@never_cache
@login_required(login_url='agora:login')
def course_detail_view(request, course_id):
    course = get_object_or_404(
        Course.objects.select_related('teacher', 'teacher__profile'),
        pk=course_id,
    )
    role = _user_role(request.user)
    is_teacher = role == UserProfile.Role.TEACHER and course.teacher_id == request.user.id
    is_enrolled_student = Enrollment.objects.filter(
        course=course,
        student=request.user,
        status=Enrollment.Status.ACTIVE,
    ).exists()

    if not is_teacher and not is_enrolled_student:
        messages.error(request, 'Você não tem permissão para acessar esta página.')
        return redirect('agora:courses_hub')

    modules = course.modules.all().order_by('order')
    activities_by_module = defaultdict(list)
    activities_without_module = []

    activities_query = Activity.objects.filter(course=course)
    if is_teacher:
        activities_query = activities_query.annotate(submission_count=Count('submissions'))
    else:
        activities_query = activities_query.filter(is_published=True).annotate(
            submission_count=Count('submissions', filter=Q(submissions__student=request.user))
        )

    activities_with_submission_counts = activities_query.order_by('due_date', 'title')

    for activity in activities_with_submission_counts:
        activity_data = {
            'id': activity.id,
            'title': activity.title,
            'description': activity.description,
            'activity_type': activity.get_activity_type_display(),
            'attachment_url': activity.attachment_url,
            'due_date': activity.due_date,
            'max_score': activity.max_score,
            'is_published': activity.is_published,
            'submission_count': activity.submission_count,
        }
        if activity.module:
            activities_by_module[activity.module.id].append(activity_data)
        else:
            activities_without_module.append(activity_data)

    modules_data = []
    for module in modules:
        modules_data.append({
            'id': module.id,
            'title': module.title,
            'description': module.description,
            'activities': activities_by_module[module.id]
        })

    active_enrollments = list(
        Enrollment.objects.select_related('student', 'student__profile')
        .filter(course=course, status=Enrollment.Status.ACTIVE)
        .order_by('student__first_name', 'student__last_name', 'student__username')
    )

    context = {
        'course': course,
        'professor_name': course.teacher.get_full_name() or course.teacher.username,
        'active_enrollments': active_enrollments,
        'student_count': len(active_enrollments),
        'is_teacher': is_teacher,
        'is_enrolled_student': is_enrolled_student,
        'modules': modules_data,
        'activities_without_module': activities_without_module,
    }
    return render(request, 'agora/course_detail.html', context)


@never_cache
@login_required(login_url='agora:login')
@user_passes_test(lambda u: _user_role(u) == UserProfile.Role.TEACHER)
def module_create_view(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    if course.teacher != request.user:
        messages.error(request, 'Você não tem permissão para criar módulos neste curso.')
        return redirect('agora:course_detail', course_id=course.id)

    if request.method == 'POST':
        form = ModuleCreateForm(request.POST)
        if form.is_valid():
            module = form.save(commit=False)
            module.course = course
            module.save()
            messages.success(request, f'Módulo "{module.title}" criado com sucesso.')
            return redirect('agora:course_detail', course_id=course.id)
    else:
        form = ModuleCreateForm(initial={'course': course})
    
    context = {
        'form': form,
        'course': course,
        'form_title': 'Criar Novo Módulo',
        'submit_button_text': 'Criar Módulo',
    }
    return render(request, 'agora/module_form.html', context)


@never_cache
@login_required(login_url='agora:login')
@user_passes_test(lambda u: _user_role(u) == UserProfile.Role.TEACHER)
def activity_create_view(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    if course.teacher != request.user:
        messages.error(request, 'Você não tem permissão para criar atividades neste curso.')
        return redirect('agora:course_detail', course_id=course.id)

    if request.method == 'POST':
        form = ActivityCreateForm(request.POST, course=course)
        if form.is_valid():
            activity = form.save(commit=False)
            activity.course = course
            activity.created_by = request.user
            activity.save()
            messages.success(request, f'Atividade/Recurso "{activity.title}" criado com sucesso.')
            return redirect('agora:course_detail', course_id=course.id)
    else:
        form = ActivityCreateForm(course=course)
    
    context = {
        'form': form,
        'course': course,
        'form_title': 'Criar Nova Atividade ou Recurso',
        'submit_button_text': 'Criar',
    }
    return render(request, 'agora/activity_form.html', context)


@never_cache
@login_required(login_url='agora:login')
@user_passes_test(lambda u: _user_role(u) == UserProfile.Role.TEACHER)
def submission_list_view(request, activity_id):
    activity = get_object_or_404(Activity.objects.select_related('course'), pk=activity_id)
    if activity.course.teacher != request.user:
        messages.error(request, 'Você não tem permissão para visualizar as submissões desta atividade.')
        return redirect('agora:course_detail', course_id=activity.course.id)

    submissions = Submission.objects.filter(activity=activity).select_related('student').order_by('-submitted_at')

    context = {
        'activity': activity,
        'submissions': submissions,
    }
    return render(request, 'agora/submission_list.html', context)


@never_cache
@login_required(login_url='agora:login')
def request_enrollment_view(request, course_id):
    if request.method != 'POST' or _user_role(request.user) != UserProfile.Role.STUDENT:
        return redirect('agora:courses_hub')

    course = get_object_or_404(Course, pk=course_id, is_published=True)
    enrollment = Enrollment.objects.filter(student=request.user, course=course).first()

    if enrollment:
        if enrollment.status == Enrollment.Status.ACTIVE:
            messages.info(request, 'Você já está matriculado nesse curso.')
            return redirect('agora:courses_hub')
        if enrollment.status == Enrollment.Status.PENDING:
            messages.info(request, 'Sua solicitação já foi enviada e ainda está pendente.')
            return redirect('agora:courses_hub')
        if enrollment.status == Enrollment.Status.COMPLETED:
            messages.info(request, 'Esse curso já consta como concluído no seu histórico.')
            return redirect('agora:courses_hub')

        enrollment.status = Enrollment.Status.PENDING
        enrollment.final_grade = None
        enrollment.full_clean()
        enrollment.save(update_fields=['status', 'final_grade'])
    else:
        enrollment = Enrollment(
            student=request.user,
            course=course,
            status=Enrollment.Status.PENDING,
        )
        enrollment.full_clean()
        enrollment.save()

    messages.success(request, f'Solicitação de matrícula enviada para {course.code}.')
    return redirect('agora:courses_hub')


@never_cache
@login_required(login_url='agora:login')
def enrollment_decision_view(request, enrollment_id, decision):
    if request.method != 'POST' or _user_role(request.user) != UserProfile.Role.TEACHER:
        return redirect('agora:courses_hub')

    enrollment = get_object_or_404(
        Enrollment.objects.select_related('course', 'student'),
        pk=enrollment_id,
        course__teacher=request.user,
    )

    if enrollment.status != Enrollment.Status.PENDING:
        messages.info(request, 'Essa solicitação já foi processada.')
        return redirect('agora:courses_hub')

    if decision == 'accept':
        enrollment.status = Enrollment.Status.ACTIVE
        enrollment.save(update_fields=['status'])
        messages.success(
            request,
            f'{enrollment.student.username} agora está matriculado em {enrollment.course.code}.',
        )
    elif decision == 'reject':
        enrollment.status = Enrollment.Status.CANCELLED
        enrollment.save(update_fields=['status'])
        messages.success(
            request,
            f'A solicitação de {enrollment.student.username} para {enrollment.course.code} foi recusada.',
        )

    return redirect('agora:courses_hub')


@never_cache
@login_required(login_url='agora:login')
def calendar_view(request):
    now = timezone.localtime()

    role = _user_role(request.user)

    if role == UserProfile.Role.TEACHER:
        return redirect('agora:index')
    
    current_year = now.year
    current_month = now.month
    month_matrix = month_calendar.monthcalendar(current_year, current_month)
    weekday_labels = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sab', 'Dom']
    month_label = date(current_year, current_month, 1).strftime('%B de %Y').capitalize()

    enrollments = list(request.user.enrollments.filter(
        status=Enrollment.Status.ACTIVE
    ).select_related('course').order_by('course__title'))
    course_ids = [enrollment.course_id for enrollment in enrollments]

    activities = list(
        Activity.objects.select_related('course')
        .filter(
            course_id__in=course_ids,
            is_published=True,
            due_date__year=current_year,
            due_date__month=current_month,
        )
        .exclude(
            submissions__student=request.user,
            submissions__status__in=[
                Submission.Status.SUBMITTED,
                Submission.Status.REVIEWED,
                Submission.Status.LATE,
            ],
        )
        .distinct()
        .order_by('due_date', 'title')
    )

    activities_by_day = defaultdict(list)
    upcoming_items = []
    today = now.date()

    for activity in activities:
        due_dt = timezone.localtime(activity.due_date) if activity.due_date else None
        if not due_dt:
            continue

        status = 'Planejada'
        tone = 'neutral'
        if due_dt.date() < today:
            status = 'Atrasada'
            tone = 'danger'
        elif due_dt.date() == today:
            status = 'Hoje'
            tone = 'warning'
        elif due_dt.date() <= today + timedelta(days=3):
            status = 'Próxima'
            tone = 'accent'

        item = {
            'title': activity.title,
            'course_code': activity.course.code,
            'course_title': activity.course.title,
            'time_label': due_dt.strftime('%H:%M'),
            'date_label': due_dt.strftime('%d/%m, %H:%M'),
            'status_label': status,
            'status_tone': tone,
        }
        activities_by_day[due_dt.day].append(item)
        upcoming_items.append(item)

    calendar_weeks = []
    for week in month_matrix:
        cells = []
        for day_number in week:
            in_month = day_number != 0
            day_items = activities_by_day.get(day_number, []) if in_month else []
            cells.append({
                    'day': day_number,
                    'in_month': in_month,
                    'is_today': in_month and day_number == today.day,
                    'items': day_items[:2],
                    'extra_count': max(len(day_items) - 2, 0),
            })

        calendar_weeks.append(cells)

    reviewed_submissions = list(
        Submission.objects.select_related('activity', 'activity__course', 'activity__course__teacher')
        .filter(
            student=request.user,
            activity__course_id__in=course_ids,
            status=Submission.Status.REVIEWED,
            score__isnull=False,
        )
        .order_by('-graded_at', '-updated_at', '-id')
    )

    grade_cards = [{
            'course_code': submission.activity.course.code,
            'course_title': submission.activity.course.title,
            'teacher_name': submission.activity.course.teacher.get_full_name() or submission.activity.course.teacher.username,
            'activity_title': submission.activity.title,
            'score': submission.score,
            'graded_at': submission.graded_at or submission.updated_at,
            'feedback': submission.feedback,
        } for submission in reviewed_submissions
    ]

    agenda_page = Paginator(upcoming_items, 3).get_page(request.GET.get('agenda_page'))
    grade_page = Paginator(grade_cards, 3).get_page(request.GET.get('grade_page'))

    context = {
        'month_label': month_label,
        'weekday_labels': weekday_labels,
        'calendar_weeks': calendar_weeks,
        'agenda_page': agenda_page,
        'grade_page': grade_page,
    }

    return render(request, 'agora/calendar.html', context)


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
