from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import render

from ..forms import SuperuserCreateUserForm


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
