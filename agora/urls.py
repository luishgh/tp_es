from django.urls import path

from .views import (
    calendar_view,
    course_detail_view,
    courses_hub_view,
    create_user_view,
    enrollment_decision_view,
    index,
    login_view,
    logout_view,
    request_enrollment_view,
)

app_name = 'agora'

urlpatterns = [
    path('', index, name='index'),
    path('calendario/', calendar_view, name='calendar'),
    path('cursos/', courses_hub_view, name='courses_hub'),
    path('cursos/<int:course_id>/pagina/', course_detail_view, name='course_detail'),
    path('cursos/<int:course_id>/solicitar-matricula/', request_enrollment_view, name='request_enrollment'),
    path('matriculas/<int:enrollment_id>/<str:decision>/', enrollment_decision_view, name='enrollment_decision'),
    path('login/', login_view, name='login'),
    path('users/create/', create_user_view, name='create_user'),
    path('logout/', logout_view, name='logout'),
]
