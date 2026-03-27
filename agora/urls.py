from django.urls import path

from .views import create_user_view, index, login_view, logout_view

app_name = 'agora'

urlpatterns = [
    path('', index, name='index'),
    path('login/', login_view, name='login'),
    path('users/create/', create_user_view, name='create_user'),
    path('logout/', logout_view, name='logout'),
]
