from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache

from ..forms import (
    AssignmentSubmissionForm,
    SubmissionReviewForm,
    AssignmentCreateForm,
    ForumMessageForm,
    ForumCreateForm,
    ModuleCreateForm,
    QuizCreateForm,
    ResourceCreateForm,
)
from ..models import (
    Answer,
    AssignmentItem,
    Course,
    CourseItem,
    Enrollment,
    ForumItem,
    ForumMessage,
    QuizOption,
    QuizQuestion,
    QuizItem,
    ResourceItem,
    Submission,
    UserProfile,
)
from .common import _user_role


def _question_is_correct(question, selected_option_ids):
    selected_ids = set(selected_option_ids)
    correct_ids = set(question.options.filter(is_correct=True).values_list('id', flat=True))
    return selected_ids == correct_ids


def _calculate_quiz_score(questions, answers):
    answers_by_question = {}
    for answer in answers:
        answers_by_question.setdefault(answer.question_id, set()).add(answer.selected_option_id)

    return round(
        sum(
            float(question.weight)
            for question in questions
            if _question_is_correct(question, answers_by_question.get(question.id, set()))
        ),
        2,
    )


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
def course_item_create_view(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    if course.teacher != request.user:
        messages.error(request, 'Você não tem permissão para criar atividades neste curso.')
        return redirect('agora:course_detail', course_id=course.id)
        # 
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
            course_item = form.save()
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
    return render(request, 'agora/course_item_form.html', context)


@never_cache
@login_required(login_url='agora:login')
def course_item_detail_view(request, course_item_id):
    course_item = get_object_or_404(
        CourseItem.objects.select_related('course', 'module', 'created_by', 'course__teacher'),
        pk=course_item_id,
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

    assignment_form = None
    forum_form = None
    quiz_questions = []
    quiz_feedback = None
    quiz_student_answers = {}
    quiz_score = None
    forum_messages = []
    material_actions = []
    submission_status = None
    current_submission = None

    if isinstance(detail, ResourceItem):
        if detail.attachment_file:
            material_actions.append({
                'label': 'Baixar arquivo',
                'url': detail.attachment_file.url,
                'tone': 'primary',
            })
        if detail.attachment_url:
            material_actions.append({
                'label': 'Abrir link',
                'url': detail.attachment_url,
                'tone': 'ghost',
            })

    if role == UserProfile.Role.STUDENT and is_enrolled_student:
        if isinstance(detail, AssignmentItem):
            current_submission = Submission.objects.filter(assignment=detail, student=request.user).first()
            if request.method == 'POST' and request.POST.get('action') == 'submit_assignment':
                assignment_form = AssignmentSubmissionForm(request.POST, request.FILES, instance=current_submission)
                if assignment_form.is_valid():
                    submission = assignment_form.save(commit=False)
                    submission.assignment = detail
                    submission.student = request.user
                    submission.status = Submission.Status.SUBMITTED
                    submission.submitted_at = timezone.now()
                    submission.save()
                    messages.success(request, 'Sua entrega foi registrada com sucesso.')
                    return redirect('agora:course_item_detail', course_item_id=course_item.id)
            else:
                assignment_form = AssignmentSubmissionForm(instance=current_submission)

            if current_submission:
                submission_status = {
                    'label': current_submission.get_status_display(),
                    'tone': 'accent' if current_submission.status in (Submission.Status.SUBMITTED, Submission.Status.REVIEWED) else 'neutral',
                    'submitted_at': current_submission.submitted_at,
                }
            else:
                submission_status = {
                    'label': 'Não iniciado',
                    'tone': 'neutral',
                    'submitted_at': None,
                }
        elif isinstance(detail, ForumItem):
            if request.method == 'POST' and request.POST.get('action') == 'post_forum_message':
                forum_form = ForumMessageForm(request.POST)
                if forum_form.is_valid():
                    forum_message = forum_form.save(commit=False)
                    forum_message.forum = detail
                    forum_message.author = request.user
                    forum_message.save()
                    messages.success(request, 'Mensagem enviada no fórum.')
                    return redirect('agora:course_item_detail', course_item_id=course_item.id)
            else:
                forum_form = ForumMessageForm()
        elif isinstance(detail, QuizItem):
            if request.method == 'POST' and request.POST.get('action') == 'submit_quiz':
                if not detail.allow_resubmissions and Answer.objects.filter(quiz=detail, student=request.user).exists():
                    messages.error(request, 'Este quiz não permite reenviar respostas.')
                    return redirect('agora:course_item_detail', course_item_id=course_item.id)

                missing_answers = []
                selected_answers = []
                questions = list(detail.questions.prefetch_related('options').all())
                for question in questions:
                    if question.question_type == QuizQuestion.QuestionType.MULTIPLE_CHOICE:
                        selected_option_ids = request.POST.getlist(f'question_{question.id}')
                        selected_options = list(question.options.filter(pk__in=selected_option_ids))
                        if len(selected_options) != len(set(selected_option_ids)) or not selected_options:
                            missing_answers.append(question.order)
                            continue
                    else:
                        selected_option_id = request.POST.get(f'question_{question.id}')
                        if not selected_option_id:
                            missing_answers.append(question.order)
                            continue
                        selected_options = list(question.options.filter(pk=selected_option_id))

                    if not selected_options:
                        missing_answers.append(question.order)
                        continue
                    selected_answers.append((question, selected_options))

                if missing_answers:
                    messages.error(
                        request,
                        'Responda todas as questões antes de enviar o quiz.'
                    )
                else:
                    with transaction.atomic():
                        Answer.objects.filter(quiz=detail, student=request.user).delete()
                        Answer.objects.bulk_create(
                            [
                                Answer(
                                    quiz=detail,
                                    question=question,
                                    student=request.user,
                                    selected_option=selected_option,
                                )
                                for question, selected_options in selected_answers
                                for selected_option in selected_options
                            ]
                        )
                    messages.success(request, 'Suas respostas do quiz foram registradas.')
                    return redirect('agora:course_item_detail', course_item_id=course_item.id)

            question_list = list(detail.questions.prefetch_related('options').all())
            student_answers_qs = list(
                Answer.objects.filter(quiz=detail, student=request.user).select_related('selected_option', 'question')
            )
            for answer in student_answers_qs:
                quiz_student_answers.setdefault(answer.question_id, set()).add(answer.selected_option_id)
            if student_answers_qs:
                quiz_score = _calculate_quiz_score(question_list, student_answers_qs)
                quiz_feedback = f'{len(quiz_student_answers)}/{detail.questions.count()} questões respondidas'
            elif not detail.allow_resubmissions:
                quiz_feedback = 'Este quiz aceita apenas uma tentativa.'

    submissions = []
    if is_teacher and isinstance(detail, AssignmentItem):
        submissions_qs = sorted(
            Submission.objects.filter(assignment=detail).select_related('student'),
            key=lambda submission: (
                submission.status == Submission.Status.REVIEWED,
                (submission.student.get_full_name() or submission.student.username).strip().lower(),
                submission.student.username.lower(),
            ),
        )
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
                'is_reviewed': submission.status == Submission.Status.REVIEWED,
            })
    if isinstance(detail, ForumItem):
        forum_messages = list(
            detail.messages.select_related('author').order_by('created_at', 'id')
        )
        if is_teacher and request.method == 'POST' and request.POST.get('action') == 'post_forum_message':
            forum_form = ForumMessageForm(request.POST)
            if forum_form.is_valid():
                forum_message = forum_form.save(commit=False)
                forum_message.forum = detail
                forum_message.author = request.user
                forum_message.save()
                messages.success(request, 'Mensagem enviada no fórum.')
                return redirect('agora:course_item_detail', course_item_id=course_item.id)
        elif is_teacher and forum_form is None:
            forum_form = ForumMessageForm()

    if isinstance(detail, QuizItem):
        questions_qs = detail.questions.prefetch_related('options').all()
        teacher_answer_counts = {}
        if is_teacher:
            for option in QuizOption.objects.filter(question__quiz=detail).annotate(total_answers=Count('answers')):
                teacher_answer_counts[option.id] = option.total_answers

        for question in questions_qs:
            quiz_questions.append({
                'id': question.id,
                'order': question.order,
                'statement': question.statement,
                'image_url': question.image.url if question.image else None,
                'question_type': question.question_type,
                'weight': question.weight,
                'options': [
                    {
                        'id': option.id,
                        'text': option.text,
                        'is_correct': option.is_correct,
                        'answer_count': teacher_answer_counts.get(option.id, 0),
                        'is_selected': option.id in quiz_student_answers.get(question.id, set()),
                    }
                    for option in question.options.all()
                ],
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
        'assignment_form': assignment_form,
        'current_submission': current_submission,
        'forum_form': forum_form,
        'forum_messages': forum_messages,
        'quiz_questions': quiz_questions,
        'quiz_feedback': quiz_feedback,
        'quiz_score': quiz_score,
        'material_actions': material_actions,
    }
    return render(request, 'agora/course_item_detail.html', context)


@never_cache
@login_required(login_url='agora:login')
def submission_review_view(request, submission_id):
    submission = get_object_or_404(
        Submission.objects.select_related(
            'assignment',
            'assignment__course',
            'assignment__module',
            'student',
            'student__profile',
            'graded_by',
        ),
        pk=submission_id,
    )

    assignment = submission.assignment
    course = assignment.course
    if course.teacher_id != request.user.id:
        messages.error(request, 'Você não tem permissão para avaliar esta entrega.')
        return redirect('agora:course_item_detail', course_item_id=assignment.id)

    if request.method == 'POST':
        form = SubmissionReviewForm(request.POST, instance=submission, assignment=assignment)
        if form.is_valid():
            reviewed_submission = form.save(commit=False)
            reviewed_submission.status = Submission.Status.REVIEWED
            reviewed_submission.graded_by = request.user
            reviewed_submission.graded_at = timezone.now()
            reviewed_submission.save()
            messages.success(request, 'Avaliação salva com sucesso.')
            return redirect('agora:course_item_detail', course_item_id=assignment.id)
    else:
        form = SubmissionReviewForm(instance=submission, assignment=assignment)

    context = {
        'submission': submission,
        'assignment': assignment,
        'course': course,
        'module': assignment.module,
        'form': form,
        'is_reviewed': submission.status == Submission.Status.REVIEWED,
    }
    return render(request, 'agora/submission_review.html', context)


@never_cache
@login_required(login_url='agora:login')
def publish_course_item_view(request, course_item_id):
    if request.method != 'POST':
        return redirect('agora:course_item_detail', course_item_id=course_item_id)

    course_item = get_object_or_404(CourseItem.objects.select_related('course'), pk=course_item_id)
    if course_item.course.teacher_id != request.user.id:
        messages.error(request, 'Você não tem permissão para publicar esta atividade.')
        return redirect('agora:course_item_detail', course_item_id=course_item.id)

    if course_item.is_published:
        messages.info(request, 'Esta atividade já está publicada.')
        return redirect('agora:course_item_detail', course_item_id=course_item.id)

    course_item.is_published = True
    course_item.save(update_fields=['is_published'])
    messages.success(request, 'Atividade publicada com sucesso.')
    return redirect('agora:course_item_detail', course_item_id=course_item.id)
