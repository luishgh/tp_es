from collections import defaultdict
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache

from ..models import Answer, AssignmentItem, CourseItem, Enrollment, QuizItem, Submission, UserProfile
from .common import _user_role


@never_cache
@login_required(login_url='agora:login')
def index(request):
    role = _user_role(request.user)

    if role == UserProfile.Role.TEACHER:
        context = _build_teacher_dashboard_context(request.user)
    else:
        context = _build_student_dashboard_context(request.user)

    course_cards = context.pop('course_cards')
    context['courses_page'] = Paginator(course_cards, 6).get_page(request.GET.get('courses_page'))

    pending_cards = context.pop('pending_cards')
    context['work_page'] = Paginator(pending_cards, 5).get_page(request.GET.get('work_page'))

    return render(request, 'agora/index.html', context)


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

    pending_by_course = {
        item['assignment__course_id']: item['total']
        for item in Submission.objects.filter(
            assignment__course_id__in=course_ids,
            assignment__is_published=True,
            assignment__due_date__lt=now,
            status__in=[Submission.Status.SUBMITTED, Submission.Status.LATE],
        )
        .values('assignment__course_id')
        .annotate(total=Count('id'))
    }

    reviewed_by_course = {
        item['assignment__course_id']: item['total']
        for item in Submission.objects.filter(
            assignment__course_id__in=course_ids,
            assignment__is_published=True,
            assignment__due_date__lt=now,
            status=Submission.Status.REVIEWED,
        )
        .values('assignment__course_id')
        .annotate(total=Count('id'))
    }

    activities_pending_review = list(
        AssignmentItem.objects.select_related('course')
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
        item['assignment_id']: item['total']
        for item in Submission.objects.filter(
            assignment__course__teacher=user,
            assignment__is_published=True,
            assignment__due_date__lt=now,
            status__in=[Submission.Status.SUBMITTED, Submission.Status.LATE],
        )
        .values('assignment_id')
        .annotate(total=Count('id'))
    }

    pending_cards = []

    for activity in activities_pending_review:
        course = activity.course
        pending_reviews = pending_review_counts.get(activity.id, 0)

        pending_cards.append({
            'id': activity.id,
            'title': activity.title,
            'course_title': course.title,
            'course_code': course.code,
            'activity_type': activity.kind_label,
            'status_label': 'Correção pendente',
            'status_tone': 'danger',
            'meta_label': f'{pending_reviews} submissão{"s" if pending_reviews != 1 else ""} pendente de correção',
        })

    course_cards = []
    for index_number, course in enumerate(courses):
        total_students = course_student_counts.get(course.id, 0)
        pending = pending_by_course.get(course.id, 0)
        reviewed = reviewed_by_course.get(course.id, 0)
        total = pending + reviewed

        progress = int((reviewed / total) * 100) if total else 0

        course_cards.append({
            'id': course.id,
            'title': course.title,
            'code': course.code,
            'progress': progress,
            'accent': ['forest', 'sand', 'sage'][index_number % 3],
            'meta_label': f'{total_students} aluno{"s" if total_students != 1 else ""} ativo{"s" if total_students != 1 else ""}',
            'progress_label': f'{reviewed}/{total} submissões corrigidas',
        })

    return {
        'course_cards': course_cards,
        'pending_cards': pending_cards,
        'courses_count': len(course_cards),
        'pending_count': sum(pending_by_course.values()),
    }


def _build_student_dashboard_context(user):
    now = timezone.localtime()

    enrollments = list(
        user.enrollments.filter(status=Enrollment.Status.ACTIVE).select_related('course').order_by('course__title')
    )
    course_ids = [enrollment.course_id for enrollment in enrollments]

    course_published_items = {
        item['course_id']: item['total']
        for item in CourseItem.objects.filter(course_id__in=course_ids, is_published=True)
        .values('course_id')
        .annotate(total=Count('id'))
    }

    answered_quiz_ids = set(
        Answer.objects.filter(student=user, quiz__course_id__in=course_ids).values_list('quiz_id', flat=True)
    )
    submitted_assignment_ids = set(
        Submission.objects.filter(
            student=user,
            assignment__course_id__in=course_ids,
            status__in=[
                Submission.Status.SUBMITTED,
                Submission.Status.REVIEWED,
                Submission.Status.LATE,
            ],
        ).values_list('assignment_id', flat=True)
    )

    pending_items = sorted(
        list(
            AssignmentItem.objects.select_related('course')
            .filter(course_id__in=course_ids, is_published=True)
            .exclude(id__in=submitted_assignment_ids)
        )
        + list(
            QuizItem.objects.select_related('course')
            .filter(course_id__in=course_ids, is_published=True)
            .exclude(id__in=answered_quiz_ids)
        ),
        key=lambda item: (item.due_date is None, item.due_date or now, item.title.lower()),
    )

    pending_count_by_course = defaultdict(int)
    pending_cards = []
    overdue_activities = 0

    for activity in pending_items:
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
            'activity_type': activity.kind_label,
            'status_label': status_label,
            'status_tone': status_tone,
            'meta_label': f'Prazo de entrega: {due_date.strftime("%d/%m, %H:%M") if due_date else "Sem data definida"}',
        })

    course_cards = []
    for index_number, enrollment in enumerate(enrollments):
        course = enrollment.course
        total_activities = course_published_items.get(course.id, 0)
        pending = pending_count_by_course.get(course.id, 0)
        progress = int((1 - pending / total_activities) * 100) if total_activities else 0

        course_cards.append({
            'id': course.id,
            'title': course.title,
            'code': course.code,
            'progress': progress,
            'accent': ['forest', 'sand', 'sage'][index_number % 3],
            'meta_label': f'Professor(a): {course.teacher.get_full_name() or course.teacher.username}',
            'progress_label': f'{pending} atividade{"" if pending == 1 else "s"} pendente{"" if pending == 1 else "s"}',
        })

    return {
        'course_cards': course_cards,
        'pending_cards': pending_cards,
        'courses_count': len(course_cards),
        'pending_count': len(pending_cards),
        'overdue_activities': overdue_activities,
    }
