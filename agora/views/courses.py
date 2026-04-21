from collections import defaultdict

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache

from ..forms import CourseCreateForm
from ..models import Answer, AssignmentItem, Course, CourseItem, Enrollment, QuizItem, Submission, UserProfile
from .common import _user_role


def _detail_due_date(course_item):
    detail = course_item.detail_object
    return getattr(detail, 'due_date', None)


def _course_detail_redirect(course_id, module_page=None, activity_page=None):
    base_url = reverse('agora:course_detail', args=[course_id])
    params = []
    if module_page:
        params.append(f'module_page={module_page}')
    if activity_page:
        params.append(f'activity_page={activity_page}')
    if not params:
        return base_url
    return f"{base_url}?{'&'.join(params)}"


def _calculate_quiz_score(quiz, answers):
    return round(
        sum(
            float(answer.question.weight)
            for answer in answers
            if answer.selected_option.is_correct
        ),
        2,
    )


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
            'pending_requests_page': Paginator(pending_requests, 3).get_page(request.GET.get('pending_requests_page')),
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

        can_request = True
        status_badge = None
        if enrollment and enrollment.status == Enrollment.Status.PENDING:
            can_request = False
            status_badge = 'Aguardando aprovação'
        elif enrollment and enrollment.status == Enrollment.Status.COMPLETED:
            can_request = False
            status_badge = 'Concluído'
        elif enrollment and enrollment.status == Enrollment.Status.CANCELLED:
            can_request = False
            status_badge = 'Solicitação recusada'

        available_courses.append(
            {
                'id': course.id,
                'code': course.code,
                'title': course.title,
                'description': course.description,
                'teacher_name': course.teacher.get_full_name() or course.teacher.username,
                'workload_hours': course.workload_hours,
                'can_request': can_request,
                'status_badge': status_badge,
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

    if request.method == 'POST' and role == UserProfile.Role.STUDENT and is_enrolled_student:
        if request.POST.get('action') == 'submit_course_quiz':
            quiz = get_object_or_404(
                QuizItem.objects.prefetch_related('questions__options'),
                pk=request.POST.get('quiz_id'),
                course=course,
                is_published=True,
            )
            module_page = request.POST.get('module_page')
            activity_page = request.POST.get('activity_page')
            questions = list(quiz.questions.order_by('order', 'id'))

            if not questions:
                messages.error(request, 'Este quiz ainda não possui pergunta cadastrada.')
                return HttpResponseRedirect(_course_detail_redirect(course.id, module_page, activity_page))

            missing_answers = []
            selected_answers = []
            for question in questions:
                selected_option_id = request.POST.get(f'quiz_{quiz.id}_question_{question.id}')
                selected_option = question.options.filter(pk=selected_option_id).first()
                if not selected_option:
                    missing_answers.append(question.order)
                    continue
                selected_answers.append((question, selected_option))

            if missing_answers:
                messages.error(request, 'Responda todas as questões antes de enviar o quiz.')
                return HttpResponseRedirect(_course_detail_redirect(course.id, module_page, activity_page))

            with transaction.atomic():
                for question, selected_option in selected_answers:
                    Answer.objects.update_or_create(
                        quiz=quiz,
                        question=question,
                        student=request.user,
                        defaults={'selected_option': selected_option},
                    )

            messages.success(request, f'Sua resposta para o quiz "{quiz.title}" foi registrada.')
            return HttpResponseRedirect(_course_detail_redirect(course.id, module_page, activity_page))

    modules = course.modules.all().order_by('order')
    items_by_module = defaultdict(list)
    items_without_module = []

    course_items_query = CourseItem.objects.filter(course=course).select_related('course', 'module', 'created_by')
    if not is_teacher:
        course_items_query = course_items_query.filter(is_published=True)

    assignment_submission_counts = {}
    if is_teacher:
        assignment_submission_counts = {
            item['id']: item['submission_count']
            for item in AssignmentItem.objects.filter(course=course)
            .annotate(submission_count=Count('submissions'))
            .values('id', 'submission_count')
        }
    else:
        assignment_submission_counts = {
            item['id']: item['submission_count']
            for item in AssignmentItem.objects.filter(course=course, is_published=True)
            .annotate(submission_count=Count('submissions', filter=Q(submissions__student=request.user)))
            .values('id', 'submission_count')
        }

    course_items = sorted(
        list(course_items_query),
        key=lambda item: (_detail_due_date(item) is None, _detail_due_date(item) or item.created_at, item.title.lower()),
    )

    student_quiz_answers = {}
    quiz_answer_counts = {}
    if is_enrolled_student and role == UserProfile.Role.STUDENT:
        for answer in Answer.objects.filter(quiz__course=course, student=request.user).select_related('selected_option'):
            student_quiz_answers[answer.question_id] = answer.selected_option_id
    if is_teacher:
        quiz_answer_counts = {
            row['selected_option_id']: row['total']
            for row in Answer.objects.filter(quiz__course=course)
            .values('selected_option_id')
            .annotate(total=Count('id'))
        }

    for course_item in course_items:
        detail = course_item.detail_object
        activity_data = {
            'id': course_item.id,
            'title': course_item.title,
            'description': course_item.description,
            'activity_type': course_item.kind_label,
            'activity_type_value': course_item.kind,
            'due_date': getattr(detail, 'due_date', None),
            'max_score': getattr(detail, 'max_score', None),
            'is_published': course_item.is_published,
            'submission_count': assignment_submission_counts.get(course_item.id, 0),
            'quiz': None,
        }
        if isinstance(detail, QuizItem):
            questions = list(detail.questions.order_by('order', 'id').prefetch_related('options'))
            if questions:
                answer_qs = Answer.objects.filter(quiz=detail, student=request.user).select_related('selected_option', 'question') if is_enrolled_student and role == UserProfile.Role.STUDENT else Answer.objects.none()
                answer_list = list(answer_qs)
                activity_data['quiz'] = {
                    'score': _calculate_quiz_score(detail, answer_list) if answer_list else None,
                    'answered_count': len(answer_list),
                    'question_count': len(questions),
                    'has_answer': bool(answer_list),
                    'questions': [
                        {
                            'id': question.id,
                            'statement': question.statement,
                            'score': question.weight,
                            'options': [
                                {
                                    'id': option.id,
                                    'text': option.text,
                                    'is_correct': option.is_correct,
                                    'answer_count': quiz_answer_counts.get(option.id, 0),
                                    'is_selected': option.id == student_quiz_answers.get(question.id),
                                }
                                for option in question.options.all()
                            ],
                        }
                        for question in questions
                    ],
                }
        if course_item.module:
            items_by_module[course_item.module.id].append(activity_data)
        else:
            items_without_module.append(activity_data)

    modules_data = []
    for module in modules:
        modules_data.append({
            'id': module.id,
            'order': module.order,
            'title': module.title,
            'description': module.description,
            'activities': items_by_module[module.id],
        })

    if items_without_module:
        modules_data.append({
            'id': 'no-module',
            'order': None,
            'title': 'Itens sem módulo',
            'description': '',
            'activities': items_without_module,
        })

    modules_page = Paginator(modules_data, 1).get_page(request.GET.get('module_page'))
    activity_page_number = request.GET.get('activity_page')
    for module in modules_page.object_list:
        module['activities_page'] = Paginator(module['activities'], 3).get_page(activity_page_number)

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
        'modules_page': modules_page,
        'modules_count': len(modules_data),
        'current_activity_page': activity_page_number or '1',
    }
    return render(request, 'agora/course_detail.html', context)


@never_cache
@login_required(login_url='agora:login')
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
