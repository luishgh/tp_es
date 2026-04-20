from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
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
                missing_answers = []
                for question in detail.questions.prefetch_related('options').all():
                    selected_option_id = request.POST.get(f'question_{question.id}')
                    if not selected_option_id:
                        missing_answers.append(question.order)
                        continue
                    selected_option = question.options.filter(pk=selected_option_id).first()
                    if not selected_option:
                        missing_answers.append(question.order)
                        continue
                    Answer.objects.update_or_create(
                        quiz=detail,
                        question=question,
                        student=request.user,
                        defaults={'selected_option': selected_option},
                    )

                if missing_answers:
                    messages.error(
                        request,
                        'Responda todas as questões antes de enviar o quiz.'
                    )
                else:
                    messages.success(request, 'Suas respostas do quiz foram registradas.')
                    return redirect('agora:course_item_detail', course_item_id=course_item.id)

            student_answers_qs = Answer.objects.filter(quiz=detail, student=request.user).select_related('selected_option', 'question')
            quiz_student_answers = {
                answer.question_id: answer.selected_option_id
                for answer in student_answers_qs
            }
            if student_answers_qs:
                total_weight = sum(float(question.weight) for question in detail.questions.all()) or 1
                earned_weight = sum(
                    float(answer.question.weight)
                    for answer in student_answers_qs
                    if answer.selected_option.is_correct
                )
                if detail.max_score is not None:
                    quiz_score = round((earned_weight / total_weight) * float(detail.max_score), 2)
                quiz_feedback = f'{len(student_answers_qs)}/{detail.questions.count()} questões respondidas'

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
                'weight': question.weight,
                'options': [
                    {
                        'id': option.id,
                        'text': option.text,
                        'is_correct': option.is_correct,
                        'answer_count': teacher_answer_counts.get(option.id, 0),
                        'is_selected': quiz_student_answers.get(question.id) == option.id,
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
