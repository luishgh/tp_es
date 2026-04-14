from django.urls import path

from .views import (
    activity_create_view,
    calendar_view,
    course_detail_view,
    courses_hub_view,
    create_user_view,
    enrollment_decision_view,
    index,
    login_view,
    logout_view,
    module_create_view,
    request_enrollment_view,
    publish_course_view,
    resource_detail_view,
    submission_list_view,
)

app_name = 'agora'

urlpatterns = [
    path('', index, name='index'),
    path('calendario/', calendar_view, name='calendar'),
    path('cursos/', courses_hub_view, name='courses_hub'),
    path('cursos/<int:course_id>/', course_detail_view, name='course_detail'),
    path('cursos/<int:course_id>/publicar/', publish_course_view, name='publish_course'),
    path('cursos/<int:course_id>/modulos/criar/', module_create_view, name='module_create'),
    path('cursos/<int:course_id>/atividades/criar/', activity_create_view, name='activity_create'),
    path('atividades/<int:activity_id>/', resource_detail_view, name='resource_detail'),
    path('atividades/<int:activity_id>/submissoes/', submission_list_view, name='submission_list'),
    path('cursos/<int:course_id>/solicitar-matricula/', request_enrollment_view, name='request_enrollment'),
    path('matriculas/<int:enrollment_id>/<str:decision>/', enrollment_decision_view, name='enrollment_decision'),
    path('login/', login_view, name='login'),
    path('users/create/', create_user_view, name='create_user'),
    path('logout/', logout_view, name='logout'),
]
