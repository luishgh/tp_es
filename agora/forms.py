from django import forms
from django.contrib.auth import get_user_model
from django.db import transaction
from decimal import Decimal
import re

from .models import (
    AssignmentItem,
    Course,
    ForumMessage,
    ForumItem,
    Module,
    QuizOption,
    QuizQuestion,
    QuizItem,
    ResourceItem,
    Submission,
    UserProfile,
)


class SuperuserCreateUserForm(forms.Form):
    username = forms.CharField(max_length=150, label='Nome de usuario')
    first_name = forms.CharField(max_length=150, label='Nome')
    last_name = forms.CharField(max_length=150, label='Sobrenome')
    email = forms.EmailField(label='Email')
    password = forms.CharField(widget=forms.PasswordInput, label='Senha')
    password_confirm = forms.CharField(widget=forms.PasswordInput, label='Confirmar senha')
    role = forms.ChoiceField(choices=UserProfile.Role.choices, label='Papel')
    cpf = forms.CharField(max_length=14, label='CPF')
    birth_date = forms.DateField(
        label='Data de nascimento',
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    phone = forms.CharField(max_length=20, label='Telefone')
    bio = forms.CharField(widget=forms.Textarea, required=False, label='Biografia')

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        user_model = get_user_model()
        if user_model.objects.filter(username=username).exists():
            raise forms.ValidationError('Esse nome de usuario ja esta em uso.')
        return username
    
    def clean_cpf(self):
        cpf = (self.cleaned_data.get('cpf') or '').strip()
        if not cpf:
            raise forms.ValidationError('Preencha o CPF.')

        digits = re.sub(r'\\D', '', cpf)
        if len(digits) != 11:
            raise forms.ValidationError('Informe um CPF válido.')

        if UserProfile.objects.filter(cpf=digits).exists():
            raise forms.ValidationError('Esse CPF já está em uso.')

        return digits

    def clean_first_name(self):
        return (self.cleaned_data.get('first_name') or '').strip()

    def clean_last_name(self):
        return (self.cleaned_data.get('last_name') or '').strip()

    def clean_email(self):
        return (self.cleaned_data.get('email') or '').strip()

    def clean_phone(self):
        return (self.cleaned_data.get('phone') or '').strip()

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        password_confirm = cleaned_data.get('password_confirm')

        if password and password_confirm and password != password_confirm:
            self.add_error('password_confirm', 'As senhas informadas nao coincidem.')

        return cleaned_data

    def save(self):
        user_model = get_user_model()
        user = user_model.objects.create_user(
            username=self.cleaned_data['username'],
            first_name=self.cleaned_data['first_name'],
            last_name=self.cleaned_data['last_name'],
            email=self.cleaned_data['email'],
            password=self.cleaned_data['password'],
            is_staff=False,
            is_superuser=False,
        )
        profile = user.profile
        profile.role = self.cleaned_data['role']
        if profile.role == UserProfile.Role.STUDENT:
            profile.ensure_academic_id(user.date_joined)
        else:
            profile.academic_id = ''
        profile.cpf = self.cleaned_data['cpf']
        profile.birth_date = self.cleaned_data['birth_date']
        profile.phone = self.cleaned_data['phone']
        profile.bio = self.cleaned_data['bio']
        profile.save(update_fields=['role', 'academic_id', 'cpf', 'birth_date', 'phone', 'bio'])
        return user


class CourseCreateForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ['code', 'title', 'description', 'syllabus', 'workload_hours', 'is_published']
        labels = {
            'code': 'Código do curso',
            'title': 'Título',
            'description': 'Descrição',
            'syllabus': 'Ementa',
            'workload_hours': 'Carga horária',
            'is_published': 'Disponível para matrículas',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'syllabus': forms.Textarea(attrs={'rows': 4}),
        }

    def clean_code(self):
        return self.cleaned_data['code'].strip().upper()

    def clean_title(self):
        return self.cleaned_data['title'].strip()


class ModuleCreateForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.course = kwargs.pop('course', None)
        super().__init__(*args, **kwargs)

        self.fields['title'].widget.attrs.update({
            'placeholder': 'Ex.: Introdução ao curso',
        })
        self.fields['description'].widget.attrs.update({
            'placeholder': 'Descreva brevemente o foco deste módulo.',
        })
        self.fields['order'].widget.attrs.update({
            'min': 1,
        })

    class Meta:
        model = Module
        fields = ['title', 'description', 'order']
        labels = {
            'title': 'Título do Módulo',
            'description': 'Descrição',
            'order': 'Ordem de exibição',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def clean_title(self):
        return self.cleaned_data['title'].strip()

    def clean(self):
        cleaned_data = super().clean()
        order = cleaned_data.get('order')

        if (
            self.course
            and order
            and Module.objects.filter(course=self.course, order=order).exclude(pk=self.instance.pk).exists()
        ):
            raise forms.ValidationError(
                f'Já existe um módulo com a ordem {order} neste curso.'
            )

        return cleaned_data


class BaseCourseActivityForm(forms.ModelForm):
    title_placeholder = ''
    description_placeholder = ''

    def __init__(self, *args, **kwargs):
        course = kwargs.pop('course', None)
        super().__init__(*args, **kwargs)

        if course and 'module' in self.fields:
            self.instance.course = course
            self.fields['module'].queryset = Module.objects.filter(course=course).order_by('order', 'title')
            self.fields['module'].required = False

        if 'title' in self.fields and self.title_placeholder:
            self.fields['title'].widget.attrs.update({'placeholder': self.title_placeholder})
        if 'description' in self.fields and self.description_placeholder:
            self.fields['description'].widget.attrs.update({'placeholder': self.description_placeholder})

    def clean_title(self):
        return self.cleaned_data['title'].strip()


class ResourceCreateForm(BaseCourseActivityForm):
    title_placeholder = 'Ex.: Slides da aula 1'
    description_placeholder = 'Explique brevemente o que o estudante encontrará neste material.'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['attachment_url'].widget.attrs.update({'placeholder': 'https://...'})
        self.fields['attachment_file'].widget.attrs.update({
            'accept': '.pdf,.doc,.docx,.ppt,.pptx,.txt,.zip,.png,.jpg,.jpeg',
        })

    class Meta:
        model = ResourceItem
        fields = ['module', 'title', 'description', 'attachment_url', 'attachment_file', 'is_published']
        labels = {
            'module': 'Módulo (opcional)',
            'title': 'Título do material',
            'description': 'Descrição',
            'attachment_url': 'Link do material',
            'attachment_file': 'Arquivo do material',
            'is_published': 'Publicar agora',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 5}),
        }

    def clean(self):
        cleaned_data = super().clean()
        attachment_url = (cleaned_data.get('attachment_url') or '').strip()
        attachment_file = cleaned_data.get('attachment_file')

        cleaned_data['attachment_url'] = attachment_url
        if not attachment_url and not attachment_file:
            raise forms.ValidationError('Informe um link ou envie um arquivo para o material.')

        return cleaned_data


class AssignmentCreateForm(BaseCourseActivityForm):
    title_placeholder = 'Ex.: Lista 1'
    description_placeholder = 'Descreva a proposta da tarefa, critérios e orientações de entrega.'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['statement_url'].widget.attrs.update({'placeholder': 'https://...'})
        self.fields['statement_file'].widget.attrs.update({
            'accept': '.pdf,.doc,.docx,.ppt,.pptx,.txt,.zip,.png,.jpg,.jpeg',
        })

    class Meta:
        model = AssignmentItem
        fields = [
            'module',
            'title',
            'description',
            'statement_url',
            'statement_file',
            'due_date',
            'max_score',
            'is_published',
        ]
        labels = {
            'module': 'Módulo (opcional)',
            'title': 'Título da tarefa',
            'description': 'Descrição',
            'statement_url': 'Link do enunciado',
            'statement_file': 'Arquivo do enunciado',
            'due_date': 'Data de entrega',
            'max_score': 'Nota máxima',
            'is_published': 'Publicar agora',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 5}),
            'due_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        cleaned_data['statement_url'] = (cleaned_data.get('statement_url') or '').strip()
        if not cleaned_data.get('due_date'):
            self.add_error('due_date', 'Informe a data de entrega da tarefa.')
        if cleaned_data.get('max_score') is None:
            self.add_error('max_score', 'Informe a nota máxima da tarefa.')
        return cleaned_data


class QuizCreateForm(BaseCourseActivityForm):
    title_placeholder = 'Ex.: Quiz 1'
    description_placeholder = 'Descreva o objetivo do quiz e as orientações principais.'
    quiz_option_count = 4

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.question_count = self._resolve_question_count()
        self.fields['question_count'] = forms.IntegerField(
            initial=self.question_count,
            min_value=1,
            widget=forms.HiddenInput(),
        )
        self.question_blocks = []
        for question_index in range(1, self.question_count + 1):
            self._add_question_fields(question_index)

    class Meta:
        model = QuizItem
        fields = ['module', 'title', 'description', 'due_date', 'allow_resubmissions', 'is_published']
        labels = {
            'module': 'Módulo (opcional)',
            'title': 'Título do quiz',
            'description': 'Descrição',
            'due_date': 'Prazo de realização',
            'allow_resubmissions': 'Permitir que estudantes reenviem respostas',
            'is_published': 'Publicar agora',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 5}),
            'due_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

    def _resolve_question_count(self):
        raw_count = None
        if self.data:
            raw_count = self.data.get('question_count')
        elif self.instance.pk:
            raw_count = self.instance.questions.count() or 1
        elif self.initial:
            raw_count = self.initial.get('question_count')

        try:
            count = int(raw_count)
        except (TypeError, ValueError):
            count = 1
        return max(1, count)

    def _add_question_fields(self, question_index):
        question_prefix = f'question_{question_index}'
        statement_name = f'{question_prefix}_statement'
        image_name = f'{question_prefix}_image'
        type_name = f'{question_prefix}_type'
        score_name = f'{question_prefix}_score'
        existing_question = None
        if self.instance.pk and not self.data:
            existing_question = self.instance.questions.order_by('order', 'id')[question_index - 1]

        statement_initial = existing_question.statement if existing_question else None
        question_type_initial = (
            existing_question.question_type if existing_question else QuizQuestion.QuestionType.SINGLE_CHOICE
        )
        score_initial = existing_question.weight if existing_question else None

        self.fields[statement_name] = forms.CharField(
            label=f'Pergunta {question_index}',
            initial=statement_initial,
            widget=forms.Textarea(
                attrs={
                    'rows': 4,
                    'placeholder': 'Digite a pergunta de múltipla escolha.',
                }
            ),
        )
        self.fields[image_name] = forms.FileField(
            label='Imagem da questão (PNG ou JPEG, opcional)',
            required=False,
        )
        self.fields[image_name].widget.attrs.update({'accept': '.png,.jpg,.jpeg,image/png,image/jpeg'})
        self.fields[type_name] = forms.ChoiceField(
            label='Tipo de questão',
            choices=QuizQuestion.QuestionType.choices,
            initial=question_type_initial,
        )
        self.fields[score_name] = forms.DecimalField(
            label='Pontuação da questão',
            min_value=Decimal('0.01'),
            decimal_places=2,
            max_digits=5,
            initial=score_initial,
            widget=forms.NumberInput(attrs={'min': '0.01', 'step': '0.01'}),
        )

        option_fields = []
        for option_index, option_label in enumerate(('A', 'B', 'C', 'D'), start=1):
            option_name = f'{question_prefix}_option_{option_index}'
            option_correct_name = f'{question_prefix}_option_{option_index}_is_correct'
            existing_option = None
            if existing_question:
                existing_option = existing_question.options.order_by('order', 'id')[option_index - 1]
            self.fields[option_name] = forms.CharField(
                label=f'Alternativa {option_label}',
                initial=existing_option.text if existing_option else None,
            )
            self.fields[option_correct_name] = forms.BooleanField(
                label=f'Alternativa {option_label} é correta',
                required=False,
                initial=existing_option.is_correct if existing_option else False,
            )
            option_fields.append(
                {
                    'text': self[option_name],
                    'is_correct': self[option_correct_name],
                }
            )

        self.question_blocks.append(
            {
                'index': question_index,
                'statement': self[statement_name],
                'image': self[image_name],
                'existing_image_url': existing_question.image.url if existing_question and existing_question.image else None,
                'question_type': self[type_name],
                'score': self[score_name],
                'options': option_fields,
            }
        )

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get('due_date'):
            self.add_error('due_date', 'Informe o prazo de realização do quiz.')

        quiz_questions = []
        for question_index in range(1, self.question_count + 1):
            question_prefix = f'question_{question_index}'
            statement_key = f'{question_prefix}_statement'
            image_key = f'{question_prefix}_image'
            type_key = f'{question_prefix}_type'
            score_key = f'{question_prefix}_score'

            statement = (cleaned_data.get(statement_key) or '').strip()
            if not statement:
                self.add_error(statement_key, 'Informe a pergunta desta questão.')
            cleaned_data[statement_key] = statement

            question_type = cleaned_data.get(type_key)
            if not question_type:
                self.add_error(type_key, 'Selecione o tipo desta questão.')

            score = cleaned_data.get(score_key)
            if score is None:
                self.add_error(score_key, 'Informe a pontuação desta questão.')

            image = cleaned_data.get(image_key)
            if image:
                file_name = image.name.lower()
                if not file_name.endswith(('.png', '.jpg', '.jpeg')):
                    self.add_error(image_key, 'Envie uma imagem PNG ou JPEG para esta questão.')

            options = []
            seen_options = set()
            correct_options = []
            for option_index in range(1, self.quiz_option_count + 1):
                option_key = f'{question_prefix}_option_{option_index}'
                option_correct_key = f'{question_prefix}_option_{option_index}_is_correct'
                option_text = (cleaned_data.get(option_key) or '').strip()
                if not option_text:
                    self.add_error(option_key, 'Preencha esta alternativa.')
                    continue

                normalized = option_text.casefold()
                if normalized in seen_options:
                    self.add_error(option_key, 'As alternativas devem ser diferentes entre si.')
                seen_options.add(normalized)
                cleaned_data[option_key] = option_text
                options.append(option_text)
                if cleaned_data.get(option_correct_key):
                    correct_options.append(option_index)

            if question_type == QuizQuestion.QuestionType.SINGLE_CHOICE and len(correct_options) != 1:
                self.add_error(type_key, 'Questões de uma resposta devem ter exatamente uma alternativa correta.')
            elif question_type == QuizQuestion.QuestionType.MULTIPLE_CHOICE and not correct_options:
                self.add_error(type_key, 'Marque pelo menos uma alternativa correta para esta questão.')

            if statement and question_type and score is not None and len(options) == self.quiz_option_count and correct_options:
                quiz_questions.append(
                    {
                        'statement': statement,
                        'image': image,
                        'question_type': question_type,
                        'score': score,
                        'correct_options': correct_options,
                        'options': options,
                    }
                )

        cleaned_data['quiz_questions'] = quiz_questions
        if not quiz_questions:
            raise forms.ValidationError('Adicione ao menos uma questão válida ao quiz.')
        return cleaned_data

    @transaction.atomic
    def save(self, commit=True):
        quiz = super().save(commit=commit)
        if not commit:
            return quiz

        if quiz.pk:
            quiz.questions.all().delete()

        total_score = Decimal('0')
        for question_order, question_data in enumerate(self.cleaned_data['quiz_questions'], start=1):
            question = QuizQuestion.objects.create(
                quiz=quiz,
                statement=question_data['statement'],
                image=question_data['image'],
                question_type=question_data['question_type'],
                order=question_order,
                weight=question_data['score'],
            )
            total_score += question_data['score']
            for option_order, option_text in enumerate(question_data['options'], start=1):
                QuizOption.objects.create(
                    question=question,
                    text=option_text,
                    is_correct=option_order in question_data['correct_options'],
                    order=option_order,
                )

        quiz.max_score = total_score
        quiz.save(update_fields=['max_score'])
        return quiz


class ForumCreateForm(BaseCourseActivityForm):
    title_placeholder = 'Ex.: Fórum de discussão da unidade'
    description_placeholder = 'Apresente o tema do debate e indique como os estudantes devem participar.'

    class Meta:
        model = ForumItem
        fields = ['module', 'title', 'description', 'is_published']
        labels = {
            'module': 'Módulo (opcional)',
            'title': 'Título do fórum',
            'description': 'Descrição',
            'is_published': 'Publicar agora',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 6}),
        }


class AssignmentSubmissionForm(forms.ModelForm):
    class Meta:
        model = Submission
        fields = ['content', 'attachment_file']
        labels = {
            'content': 'Observações da entrega',
            'attachment_file': 'Arquivo da entrega',
        }
        widgets = {
            'content': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Se quiser, adicione um comentário para o professor.'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['attachment_file'].widget.attrs.update({
            'accept': '.pdf,.doc,.docx,.ppt,.pptx,.txt,.zip,.png,.jpg,.jpeg',
        })

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get('content') and not cleaned_data.get('attachment_file') and not getattr(self.instance, 'attachment_file', None):
            raise forms.ValidationError('Envie um arquivo ou escreva uma observação para registrar a entrega.')
        return cleaned_data


class SubmissionReviewForm(forms.ModelForm):
    class Meta:
        model = Submission
        fields = ['score', 'feedback']
        labels = {
            'score': 'Nota atribuída',
            'feedback': 'Feedback para o estudante',
        }
        widgets = {
            'feedback': forms.Textarea(attrs={'rows': 5, 'placeholder': 'Escreva comentários sobre a entrega, pontos fortes e o que pode melhorar.'}),
        }

    def __init__(self, *args, **kwargs):
        self.assignment = kwargs.pop('assignment', None)
        super().__init__(*args, **kwargs)
        self.fields['score'].required = True
        self.fields['score'].widget.attrs.update({
            'min': 0,
            'step': '0.01',
        })

        if self.assignment and self.assignment.max_score is not None:
            self.fields['score'].widget.attrs['max'] = self.assignment.max_score
            self.fields['score'].help_text = f'Informe uma nota entre 0 e {self.assignment.max_score}.'

    def clean_score(self):
        score = self.cleaned_data.get('score')
        if score is None:
            raise forms.ValidationError('Informe a nota da entrega.')

        if self.assignment and self.assignment.max_score is not None and score > self.assignment.max_score:
            raise forms.ValidationError(
                f'A nota não pode ser maior que {self.assignment.max_score}.'
            )
        return score


class ForumMessageForm(forms.ModelForm):
    class Meta:
        model = ForumMessage
        fields = ['content']
        labels = {
            'content': 'Nova mensagem',
        }
        widgets = {
            'content': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Escreva sua mensagem para iniciar ou continuar a discussão.'}),
        }

    def clean_content(self):
        content = (self.cleaned_data.get('content') or '').strip()
        if not content:
            raise forms.ValidationError('Escreva uma mensagem antes de enviar.')
        return content
