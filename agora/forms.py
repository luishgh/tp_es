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
