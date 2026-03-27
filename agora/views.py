from django.contrib.auth import authenticate, login
from django.middleware.csrf import get_token
from django.shortcuts import redirect, render


def login_view(request):
    context = {
        'error_message': '',
        'initial_username': '',
        'csrf_token_value': get_token(request),
    }

    if request.user.is_authenticated:
        return redirect('agora:index')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)

        context['initial_username'] = username

        if user is not None:
            login(request, user)
            return redirect('agora:index')

        context['error_message'] = 'Usuário ou senha inválidos.'

    return render(request, 'agora/login.html', context)


def index(request):
    return render(request, 'agora/index.html')
