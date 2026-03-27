from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import user_passes_test
from django.middleware.csrf import get_token
from django.shortcuts import redirect, render

from .forms import SuperuserCreateUserForm


def login_view(request):
    context = {
        'active_form': 'login',
        'error_message': '',
        'initial_username': '',
        'initial_register_username': '',
        'initial_register_email': '',
        'csrf_token_value': get_token(request),
    }

    if request.user.is_authenticated:
        return redirect('agora:index')

    if request.method == 'POST':
        action = request.POST.get('action', 'login')

        if action == 'register':
            user_model = get_user_model()
            username = request.POST.get('register_username', '').strip()
            email = request.POST.get('register_email', '').strip()
            password = request.POST.get('register_password', '')
            password_confirm = request.POST.get('register_password_confirm', '')

            context['active_form'] = 'register'
            context['initial_register_username'] = username
            context['initial_register_email'] = email

            if not username or not password:
                context['error_message'] = 'Preencha usuário e senha para criar a conta.'
            elif password != password_confirm:
                context['error_message'] = 'As senhas informadas não coincidem.'
            elif user_model.objects.filter(username=username).exists():
                context['error_message'] = 'Esse nome de usuário já está em uso.'
            else:
                user = user_model.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                )
                login(request, user)
                return redirect('agora:index')
        else:
            username = request.POST.get('username', '').strip()
            password = request.POST.get('password', '')
            user = authenticate(request, username=username, password=password)

            context['initial_username'] = username

            if user is not None:
                login(request, user)
                return redirect('agora:index')

            context['error_message'] = 'Usuario ou senha invalidos.'

    return render(request, 'agora/login.html', context)


def index(request):
    return render(request, 'agora/index.html')


@user_passes_test(lambda user: user.is_authenticated and user.is_superuser)
def create_user_view(request):
    form = SuperuserCreateUserForm(request.POST or None)
    created_user = None

    if request.method == 'POST' and form.is_valid():
        created_user = form.save()
        form = SuperuserCreateUserForm()

    return render(
        request,
        'agora/create_user.html',
        {
            'form': form,
            'created_user': created_user,
        },
    )


def logout_view(request):
    if request.method == 'POST':
        logout(request)

    return redirect('agora:index')
