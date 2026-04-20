from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache

from ..forms import (
    AssignmentCreateForm,
    ForumCreateForm,
    ModuleCreateForm,
    QuizCreateForm,
    ResourceCreateForm,
)
from ..models import Activity, Course, Enrollment, Submission, UserProfile
from .common import _user_role


ACTIVITY_CREATE_CONFIG = {
    Activity.Type.RESOURCE: {
        'form_class': ResourceCreateForm,
        'title': 'Criar Novo Material',
        'submit_label': 'Criar Material',
        'button_label': 'Material',
        'description': 'Publique links, leituras, slides e materiais de apoio.',
    },
    Activity.Type.ASSIGNMENT: {
        'form_class': AssignmentCreateForm,
        'title': 'Criar Nova Tarefa',
        'submit_label': 'Criar Tarefa',
        'button_label': 'Tarefa',
        'description': 'Defina uma entrega com prazo e nota máxima.',
    },
    Activity.Type.QUIZ: {
        'form_class': QuizCreateForm,
        'title': 'Criar Novo Quiz',
        'submit_label': 'Criar Quiz',
        'button_label': 'Quiz',
        'description': 'Cadastre um quiz com prazo e pontuação.',
    },
    Activity.Type.FORUM: {
        'form_class': ForumCreateForm,
        'title': 'Criar Novo Fórum',
        'submit_label': 'Criar Fórum',
        'button_label': 'Fórum',
        'description': 'Abra um espaço de discussão entre os estudantes.',
    },
}


@never_cache
@login_required(login_url='agora:login')
def module_create_view(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    if course.teacher != request.user:
        messages.error(request, 'Você não tem permissão para criar módulos neste curso.')
        return redirect('agora:course_detail', course_id=course.id)

    if request.method == 'POST':
        form = ModuleCreateForm(request.POST, course=course)
        if form.is_valid():
            module = form.save(commit=False)
            module.course = course
            module.save()
            messages.success(request, f'Módulo "{module.title}" criado com sucesso.')
            return redirect('agora:course_detail', course_id=course.id)
    else:
        form = ModuleCreateForm(course=course, initial={'order': course.modules.count() + 1})

    context = {
        'form': form,
        'course': course,
        'form_title': 'Criar Novo Módulo',
        'submit_button_text': 'Criar Módulo',
    }
    return render(request, 'agora/module_form.html', context)


@never_cache
@login_required(login_url='agora:login')
def activity_create_view(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    if course.teacher != request.user:
        messages.error(request, 'Você não tem permissão para criar atividades neste curso.')
        return redirect('agora:course_detail', course_id=course.id)

    selected_type = request.POST.get('activity_kind') or request.GET.get('type') or Activity.Type.RESOURCE
    if selected_type not in ACTIVITY_CREATE_CONFIG:
        selected_type = Activity.Type.RESOURCE

    selected_config = ACTIVITY_CREATE_CONFIG[selected_type]
    form_class = selected_config['form_class']

    if request.method == 'POST':
        form = form_class(request.POST, course=course)
        form.instance.created_by = request.user
        form.instance.course = course
        form.instance.activity_type = selected_type
        if form.is_valid():
            activity = form.save(commit=False)
            activity.activity_type = selected_type
            activity.created_by = request.user
            activity.course = course
            activity.save()
            messages.success(request, f'{activity.get_activity_type_display()} "{activity.title}" criado com sucesso.')
            return redirect('agora:course_detail', course_id=course.id)
    else:
        form = form_class(course=course)
        form.instance.created_by = request.user
        form.instance.course = course
        form.instance.activity_type = selected_type

    context = {
        'form': form,
        'course': course,
        'form_title': selected_config['title'],
        'submit_button_text': selected_config['submit_label'],
        'selected_type': selected_type,
        'activity_type_options': [
            {
                'value': activity_type,
                'label': config['button_label'],
                'description': config['description'],
                'url': f"?type={activity_type}",
                'is_selected': activity_type == selected_type,
            }
            for activity_type, config in ACTIVITY_CREATE_CONFIG.items()
        ],
    }
    return render(request, 'agora/activity_form.html', context)


@never_cache
@login_required(login_url='agora:login')
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
def resource_detail_view(request, activity_id):
    activity = get_object_or_404(
        Activity.objects.select_related('course', 'module', 'created_by', 'course__teacher'),
        pk=activity_id,
    )

    role = _user_role(request.user)
    is_teacher = role == UserProfile.Role.TEACHER and activity.course.teacher_id == request.user.id
    is_enrolled_student = Enrollment.objects.filter(
        course=activity.course,
        student=request.user,
        status=Enrollment.Status.ACTIVE,
    ).exists()

    if not is_teacher:
        if role != UserProfile.Role.STUDENT or not is_enrolled_student:
            messages.error(request, 'Você não tem permissão para acessar esta atividade.')
            return redirect('agora:courses_hub')
        if not activity.is_published:
            messages.error(request, 'Você não tem permissão para acessar esta atividade.')
            return redirect('agora:courses_hub')

    submission_status = None
    if role == UserProfile.Role.STUDENT and is_enrolled_student:
        submission = Submission.objects.filter(activity=activity, student=request.user).first()
        if submission:
            submission_status = {
                'label': submission.get_status_display(),
                'tone': 'accent' if submission.status in (Submission.Status.SUBMITTED, Submission.Status.REVIEWED) else 'neutral',
                'submitted_at': submission.submitted_at,
            }
        else:
            submission_status = {
                'label': 'Não iniciado',
                'tone': 'neutral',
                'submitted_at': None,
            }

    submissions = []
    if is_teacher and activity.activity_type == Activity.Type.ASSIGNMENT:
        submissions_qs = Submission.objects.filter(activity=activity).select_related('student').order_by('-submitted_at', '-updated_at')
        for submission in submissions_qs:
            if submission.status == Submission.Status.REVIEWED:
                tone = 'accent'
            elif submission.status in (Submission.Status.SUBMITTED, Submission.Status.LATE):
                tone = 'warning'
            else:
                tone = 'neutral'

            submissions.append({
                'id': submission.id,
                'student_name': submission.student.get_full_name() or submission.student.username,
                'status_label': submission.get_status_display(),
                'status_tone': tone,
                'submitted_at': submission.submitted_at,
                'score': submission.score,
            })

    context = {
        'activity': activity,
        'course': activity.course,
        'module': activity.module,
        'is_teacher': is_teacher,
        'is_student': role == UserProfile.Role.STUDENT,
        'submission_status': submission_status,
        'submissions': submissions,
    }
    return render(request, 'agora/resource_detail.html', context)


@never_cache
@login_required(login_url='agora:login')
def publish_activity_view(request, activity_id):
    if request.method != 'POST':
        return redirect('agora:resource_detail', activity_id=activity_id)

    activity = get_object_or_404(Activity.objects.select_related('course'), pk=activity_id)
    if activity.course.teacher_id != request.user.id:
        messages.error(request, 'Você não tem permissão para publicar esta atividade.')
        return redirect('agora:resource_detail', activity_id=activity.id)

    if activity.is_published:
        messages.info(request, 'Esta atividade já está publicada.')
        return redirect('agora:resource_detail', activity_id=activity.id)

    activity.is_published = True
    activity.save(update_fields=['is_published'])
    messages.success(request, 'Atividade publicada com sucesso.')
    return redirect('agora:resource_detail', activity_id=activity.id)
