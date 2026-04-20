from collections import defaultdict

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache

from ..forms import CourseCreateForm
from ..models import Activity, Course, Enrollment, Submission, UserProfile
from .common import _user_role


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

        taught_courses = list(request.user.courses_taught.all().order_by('title'))
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
            .filter(course__teacher=request.user, status=Enrollment.Status.PENDING)
            .order_by('course__title', 'student__username')
        )

        taught_course_cards = [
            {
                'id': course.id,
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
        Course.objects.select_related('teacher').filter(is_published=True).order_by('title')
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
    course = get_object_or_404(Course.objects.select_related('teacher', 'teacher__profile'), pk=course_id)
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
            'activity_type_value': activity.activity_type,
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
            'activities': activities_by_module[module.id],
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
def publish_course_view(request, course_id):
    if request.method != 'POST':
        return redirect('agora:course_detail', course_id=course_id)

    course = get_object_or_404(Course, pk=course_id)
    if course.teacher != request.user:
        messages.error(request, 'Você não tem permissão para publicar este curso.')
        return redirect('agora:course_detail', course_id=course.id)

    if course.is_published:
        messages.info(request, 'Este curso já está publicado.')
        return redirect('agora:course_detail', course_id=course.id)

    course.is_published = True
    course.save(update_fields=['is_published'])
    messages.success(request, f'{course.code} foi publicado com sucesso.')
    return redirect('agora:course_detail', course_id=course.id)


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
        enrollment = Enrollment(student=request.user, course=course, status=Enrollment.Status.PENDING)
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
