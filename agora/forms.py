from django import forms
from django.contrib.auth import get_user_model

from .models import Activity, Course, Module, UserProfile


class SuperuserCreateUserForm(forms.Form):
    username = forms.CharField(max_length=150, label='Nome de usuario')
    first_name = forms.CharField(max_length=150, required=False, label='Nome')
    last_name = forms.CharField(max_length=150, required=False, label='Sobrenome')
    email = forms.EmailField(required=False, label='Email')
    password = forms.CharField(widget=forms.PasswordInput, label='Senha')
    password_confirm = forms.CharField(widget=forms.PasswordInput, label='Confirmar senha')
    role = forms.ChoiceField(choices=UserProfile.Role.choices, label='Papel')
    academic_id = forms.CharField(max_length=30, required=False, label='Matricula')
    bio = forms.CharField(widget=forms.Textarea, required=False, label='Biografia')

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        user_model = get_user_model()
        if user_model.objects.filter(username=username).exists():
            raise forms.ValidationError('Esse nome de usuario ja esta em uso.')
        return username

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
        profile.academic_id = self.cleaned_data['academic_id']
        profile.bio = self.cleaned_data['bio']
        profile.save()
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


class ActivityCreateForm(forms.ModelForm):
    class Meta:
        model = Activity
        fields = [
            'module',
            'title',
            'description',
            'activity_type',
            'attachment_url',
            'due_date',
            'max_score',
            'is_published',
        ]
        labels = {
            'module': 'Módulo (opcional)',
            'title': 'Título da Atividade/Recurso',
            'description': 'Descrição',
            'activity_type': 'Tipo',
            'attachment_url': 'Link do Anexo (para recursos)',
            'due_date': 'Data de Entrega (para tarefas)',
            'max_score': 'Nota Máxima',
            'is_published': 'Publicar agora',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'due_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

    def __init__(self, *args, **kwargs):
        course = kwargs.pop('course', None)
        super().__init__(*args, **kwargs)
        if course:
            self.instance.course = course
            self.fields['module'].queryset = Module.objects.filter(course=course).order_by('order', 'title')
            self.fields['module'].required = False

        activity_type_field = self.fields.get('activity_type')
        if activity_type_field:
            activity_type_field.choices = [('', 'Selecione o tipo')] + list(Activity.Type.choices)
            activity_type_field.widget.attrs['class'] = (
                (activity_type_field.widget.attrs.get('class', '') + ' js-activity-type').strip()
            )
            if not self.is_bound and not getattr(self.instance, 'pk', None):
                activity_type_field.initial = ''

    def clean(self):
        cleaned_data = super().clean()
        activity_type = cleaned_data.get('activity_type')

        if activity_type == Activity.Type.ASSIGNMENT:
            attachment_url = cleaned_data.get('attachment_url', '')
            if attachment_url:
                cleaned_data['attachment_url'] = attachment_url.strip()
            if not cleaned_data.get('due_date'):
                self.add_error('due_date', 'Informe a data de entrega para uma tarefa.')
        elif activity_type == Activity.Type.RESOURCE:
            if not cleaned_data.get('attachment_url'):
                self.add_error('attachment_url', 'Informe o link do material.')
            cleaned_data['due_date'] = None
            cleaned_data['max_score'] = 0
        elif activity_type in (None, ''):
            self.add_error('activity_type', 'Selecione o tipo.')
        else:
            self.add_error('activity_type', 'Tipo não suportado.')

        return cleaned_data
