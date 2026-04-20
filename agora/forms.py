from django import forms
from django.contrib.auth import get_user_model
import re

from .models import (
    AssignmentItem,
    Course,
    ForumItem,
    Module,
    QuizItem,
    ResourceItem,
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

    class Meta:
        model = QuizItem
        fields = ['module', 'title', 'description', 'due_date', 'max_score', 'is_published']
        labels = {
            'module': 'Módulo (opcional)',
            'title': 'Título do quiz',
            'description': 'Descrição',
            'due_date': 'Prazo de realização',
            'max_score': 'Pontuação máxima',
            'is_published': 'Publicar agora',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 5}),
            'due_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get('due_date'):
            self.add_error('due_date', 'Informe o prazo de realização do quiz.')
        if cleaned_data.get('max_score') is None:
            self.add_error('max_score', 'Informe a pontuação máxima do quiz.')
        return cleaned_data


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
