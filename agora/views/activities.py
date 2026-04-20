from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache

from ..forms import ActivityCreateForm, ModuleCreateForm
from ..models import Activity, Course, Enrollment, Submission, UserProfile
from .common import _user_role


@never_cache
@login_required(login_url='agora:login')
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
def activity_create_view(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    if course.teacher != request.user:
        messages.error(request, 'Você não tem permissão para criar atividades neste curso.')
        return redirect('agora:course_detail', course_id=course.id)

    if request.method == 'POST':
        form = ActivityCreateForm(request.POST, course=course)
        form.instance.created_by = request.user
        form.instance.course = course
        if form.is_valid():
            activity = form.save(commit=False)
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
