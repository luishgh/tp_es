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
from ..models import (
    AssignmentItem,
    Course,
    CourseItem,
    Enrollment,
    ForumItem,
    QuizItem,
    ResourceItem,
    Submission,
    UserProfile,
)
from .common import _user_role


ACTIVITY_CREATE_CONFIG = {
    'resource': {
        'form_class': ResourceCreateForm,
        'model_class': ResourceItem,
        'title': 'Criar Novo Material',
        'submit_label': 'Criar Material',
        'button_label': 'Material',
        'description': 'Publique links, leituras, slides e materiais de apoio.',
    },
    'assignment': {
        'form_class': AssignmentCreateForm,
        'model_class': AssignmentItem,
        'title': 'Criar Nova Tarefa',
        'submit_label': 'Criar Tarefa',
        'button_label': 'Tarefa',
        'description': 'Defina uma entrega com prazo e nota máxima.',
    },
    'quiz': {
        'form_class': QuizCreateForm,
        'model_class': QuizItem,
        'title': 'Criar Novo Quiz',
        'submit_label': 'Criar Quiz',
        'button_label': 'Quiz',
        'description': 'Cadastre um quiz com prazo e questões objetivas.',
    },
    'forum': {
        'form_class': ForumCreateForm,
        'model_class': ForumItem,
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

    selected_type = request.POST.get('activity_kind') or request.GET.get('type') or 'resource'
    if selected_type not in ACTIVITY_CREATE_CONFIG:
        selected_type = 'resource'

    selected_config = ACTIVITY_CREATE_CONFIG[selected_type]
    form_class = selected_config['form_class']

    if request.method == 'POST':
        form = form_class(request.POST, request.FILES, course=course)
        form.instance.created_by = request.user
        form.instance.course = course
        if form.is_valid():
            course_item = form.save(commit=False)
            course_item.created_by = request.user
            course_item.course = course
            course_item.save()
            messages.success(request, f'{course_item.kind_label} "{course_item.title}" criado com sucesso.')
            return redirect('agora:course_detail', course_id=course.id)
    else:
        form = form_class(course=course)
        form.instance.created_by = request.user
        form.instance.course = course

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
    assignment = get_object_or_404(
        AssignmentItem.objects.select_related('course'),
        pk=activity_id,
    )
    if assignment.course.teacher != request.user:
        messages.error(request, 'Você não tem permissão para visualizar as submissões desta atividade.')
        return redirect('agora:course_detail', course_id=assignment.course.id)

    submissions = Submission.objects.filter(assignment=assignment).select_related('student').order_by('-submitted_at')

    context = {
        'activity': assignment,
        'detail': assignment,
        'submissions': submissions,
    }
    return render(request, 'agora/submission_list.html', context)


@never_cache
@login_required(login_url='agora:login')
def resource_detail_view(request, activity_id):
    course_item = get_object_or_404(
        CourseItem.objects.select_related('course', 'module', 'created_by', 'course__teacher'),
        pk=activity_id,
    )
    detail = course_item.detail_object

    role = _user_role(request.user)
    is_teacher = role == UserProfile.Role.TEACHER and course_item.course.teacher_id == request.user.id
    is_enrolled_student = Enrollment.objects.filter(
        course=course_item.course,
        student=request.user,
        status=Enrollment.Status.ACTIVE,
    ).exists()

    if not is_teacher:
        if role != UserProfile.Role.STUDENT or not is_enrolled_student:
            messages.error(request, 'Você não tem permissão para acessar esta atividade.')
            return redirect('agora:courses_hub')
        if not course_item.is_published:
            messages.error(request, 'Você não tem permissão para acessar esta atividade.')
            return redirect('agora:courses_hub')

    submission_status = None
    if role == UserProfile.Role.STUDENT and is_enrolled_student:
        if isinstance(detail, AssignmentItem):
            submission = Submission.objects.filter(assignment=detail, student=request.user).first()
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
    if is_teacher and isinstance(detail, AssignmentItem):
        submissions_qs = Submission.objects.filter(assignment=detail).select_related('student').order_by('-submitted_at', '-updated_at')
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
        'activity': course_item,
        'detail': detail,
        'course': course_item.course,
        'module': course_item.module,
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

    course_item = get_object_or_404(CourseItem.objects.select_related('course'), pk=activity_id)
    if course_item.course.teacher_id != request.user.id:
        messages.error(request, 'Você não tem permissão para publicar esta atividade.')
        return redirect('agora:resource_detail', activity_id=course_item.id)

    if course_item.is_published:
        messages.info(request, 'Esta atividade já está publicada.')
        return redirect('agora:resource_detail', activity_id=course_item.id)

    course_item.is_published = True
    course_item.save(update_fields=['is_published'])
    messages.success(request, 'Atividade publicada com sucesso.')
    return redirect('agora:resource_detail', activity_id=course_item.id)
