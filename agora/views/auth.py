from datetime import datetime

from django.contrib.auth import authenticate, get_user_model, login, logout
from django.middleware.csrf import get_token
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache

from ..models import UserProfile


@never_cache
def login_view(request):
    if request.user.is_authenticated:
        return redirect('agora:index')

    context = {
        'active_form': 'login',
        'error_message': '',
        'initial_username': '',
        'initial_register_username': '',
        'initial_register_first_name': '',
        'initial_register_last_name': '',
        'initial_register_email': '',
        'initial_register_cpf': '',
        'initial_register_birth_date': '',
        'initial_register_phone': '',
        'initial_register_bio': '',
        'csrf_token_value': get_token(request),
    }

    if request.method == 'POST':
        action = request.POST.get('action', 'login')

        if action == 'register':
            user_model = get_user_model()
            username = request.POST.get('register_username', '').strip()
            first_name = request.POST.get('register_first_name', '').strip()
            last_name = request.POST.get('register_last_name', '').strip()
            email = request.POST.get('register_email', '').strip()
            cpf = request.POST.get('register_cpf', '').strip()
            birth_date_raw = request.POST.get('register_birth_date', '').strip()
            phone = request.POST.get('register_phone', '').strip()
            bio = request.POST.get('register_bio', '').strip()
            password = request.POST.get('register_password', '')
            password_confirm = request.POST.get('register_password_confirm', '')
            birth_date = None
            cpf_digits = ''.join(character for character in cpf if character.isdigit())

            context['active_form'] = 'register'
            context['initial_register_username'] = username
            context['initial_register_first_name'] = first_name
            context['initial_register_last_name'] = last_name
            context['initial_register_email'] = email
            context['initial_register_cpf'] = cpf
            context['initial_register_birth_date'] = birth_date_raw
            context['initial_register_phone'] = phone
            context['initial_register_bio'] = bio

            if not username or not password:
                context['error_message'] = 'Preencha usuário e senha para criar a conta.'
            elif not first_name or not last_name:
                context['error_message'] = 'Preencha nome e sobrenome.'
            elif not email:
                context['error_message'] = 'Preencha o email.'
            elif not cpf:
                context['error_message'] = 'Preencha o CPF.'
            elif len(cpf_digits) != 11:
                context['error_message'] = 'Informe um CPF válido.'
            elif not birth_date_raw:
                context['error_message'] = 'Preencha a data de nascimento.'
            elif not phone:
                context['error_message'] = 'Preencha o telefone.'
            elif password != password_confirm:
                context['error_message'] = 'As senhas informadas não coincidem.'
            elif user_model.objects.filter(username=username).exists():
                context['error_message'] = 'Esse nome de usuário já está em uso.'
            elif cpf_digits and UserProfile.objects.filter(cpf=cpf_digits).exists():
                context['error_message'] = 'Esse CPF já está em uso.'
            else:
                if birth_date_raw:
                    try:
                        birth_date = datetime.strptime(birth_date_raw, '%Y-%m-%d').date()
                    except ValueError:
                        context['error_message'] = 'Informe uma data de nascimento válida.'

            if action == 'register' and not context['error_message']:
                user = user_model.objects.create_user(
                    username=username,
                    first_name=first_name,
                    last_name=last_name,
                    email=email,
                    password=password,
                )
                user.profile.role = UserProfile.Role.STUDENT
                user.profile.cpf = cpf_digits
                user.profile.birth_date = birth_date
                user.profile.phone = phone
                user.profile.bio = bio
                user.profile.ensure_academic_id(user.date_joined)
                user.profile.save(update_fields=['role', 'cpf', 'birth_date', 'phone', 'bio', 'academic_id'])
                login(request, user)
                return redirect('agora:index')
        else:
            username = request.POST.get('username', '').strip()
            password = request.POST.get('password', '')
            user = _authenticate_by_username_or_academic_id(
                request=request,
                identifier=username,
                password=password,
            )

            context['initial_username'] = username

            if user is not None:
                login(request, user)
                return redirect('agora:index')

            context['error_message'] = 'Usuário ou senha inválidos.'

    return render(request, 'agora/login.html', context)


def _authenticate_by_username_or_academic_id(request, identifier, password):
    user = authenticate(request, username=identifier, password=password)
    if user is not None:
        return user

    profile = UserProfile.objects.select_related('user').filter(academic_id=identifier).first()
    if profile is None:
        return None

    return authenticate(request, username=profile.user.username, password=password)


@never_cache
def logout_view(request):
    if request.method == 'POST':
        logout(request)

    return redirect('agora:index')
