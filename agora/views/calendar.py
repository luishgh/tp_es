from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache

from ..models import Answer, AssignmentItem, Enrollment, QuizItem, Submission, UserProfile
from .common import _user_role


_SUBMITTED_STATUSES = {
    Submission.Status.SUBMITTED,
    Submission.Status.REVIEWED,
    Submission.Status.LATE,
}


@never_cache
@login_required(login_url='agora:login')
def calendar_view(request):
    role = _user_role(request.user)

    if role == UserProfile.Role.TEACHER:
        return redirect('agora:index')

    weekday_labels = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sab', 'Dom']

    enrollments = list(
        request.user.enrollments.filter(
            status=Enrollment.Status.ACTIVE,
        ).select_related('course').order_by('course__title')
    )
    course_ids = [enrollment.course_id for enrollment in enrollments]

    if not course_ids:
        return render(
            request,
            'agora/calendar.html',
            {
                'weekday_labels': weekday_labels,
                'calendar_items': [],
                'agenda_items': [],
                'grade_cards': [],
            },
        )

    assignments = list(
        AssignmentItem.objects.select_related('course')
        .filter(
            course_id__in=course_ids,
            is_published=True,
            due_date__isnull=False,
        )
        .distinct()
    )

    quizzes = list(
        QuizItem.objects.select_related('course')
        .filter(
            course_id__in=course_ids,
            is_published=True,
            due_date__isnull=False,
        )
        .distinct()
    )

    submitted_assignment_ids = set(
        Submission.objects.filter(
            student=request.user,
            assignment__in=assignments,
            status__in=_SUBMITTED_STATUSES,
        ).values_list('assignment_id', flat=True),
    )

    answered_quiz_ids = set(
        Answer.objects.filter(student=request.user, quiz__in=quizzes).values_list('quiz_id', flat=True),
    )

    def build_calendar_item(item):
        due_dt = timezone.localtime(item.due_date) if item.due_date else None
        if not due_dt:
            return None

        is_sent = (
            item.id in submitted_assignment_ids
            if isinstance(item, AssignmentItem)
            else item.id in answered_quiz_ids
        )

        return {
            'id': item.id,
            'detail_url': reverse('agora:course_item_detail', args=[item.id]),
            'title': item.title,
            'course_code': item.course.code,
            'course_title': item.course.title,
            'due_iso': due_dt.isoformat(),
            '_due_sort': due_dt,
            'time_label': due_dt.strftime('%H:%M'),
            'date_label': due_dt.strftime('%d/%m, %H:%M'),
            'status_label': 'Enviada' if is_sent else 'Pendente',
            'status_tone': 'sent' if is_sent else 'pending',
        }

    raw_items = [build_calendar_item(item) for item in assignments + quizzes]
    items = [item for item in raw_items if item is not None]

    items = sorted(
        items,
        key=lambda item: (item['_due_sort'], item['course_code'], item['title']),
    )
    for item in items:
        item.pop('_due_sort', None)
    calendar_items = list(items)

    agenda_items = [
        item for item in calendar_items
        if item['status_tone'] == 'pending'
    ]

    reviewed_submissions = list(
        Submission.objects.select_related('assignment', 'assignment__course', 'assignment__course__teacher')
        .filter(
            student=request.user,
            assignment__course_id__in=course_ids,
            status=Submission.Status.REVIEWED,
            score__isnull=False,
            graded_at__isnull=False,
        )
        .order_by('-graded_at', '-updated_at', '-id')
    )

    grade_cards = [
        {
            'id': submission.assignment.id,
            'detail_url': reverse('agora:course_item_detail', args=[submission.assignment.id]),
            'course_code': submission.assignment.course.code,
            'course_title': submission.assignment.course.title,
            'teacher_name': submission.assignment.course.teacher.get_full_name() or submission.assignment.course.teacher.username,
            'activity_title': submission.assignment.title,
            'score': submission.score,
            'graded_at': submission.graded_at,
            'feedback': submission.feedback,
        }
        for submission in reviewed_submissions
    ]

    context = {
        'weekday_labels': weekday_labels,
        'calendar_items': calendar_items,
        'agenda_items': agenda_items[:3],
        'grade_cards': grade_cards[:3],
    }

    return render(request, 'agora/calendar.html', context)
