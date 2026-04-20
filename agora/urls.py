from django.urls import path

from .views import *

app_name = 'agora'

urlpatterns = [
    path('', index, name='index'),
    path('calendario/', calendar_view, name='calendar'),
    path('cursos/', courses_hub_view, name='courses_hub'),
    path('cursos/<int:course_id>/', course_detail_view, name='course_detail'),
    path('cursos/<int:course_id>/publicar/', publish_course_view, name='publish_course'),
    path('cursos/<int:course_id>/modulos/criar/', module_create_view, name='module_create'),
    path('cursos/<int:course_id>/itens/criar/', course_item_create_view, name='course_item_create'),
    path('itens/<int:course_item_id>/', course_item_detail_view, name='course_item_detail'),
    path('itens/<int:course_item_id>/publicar/', publish_course_item_view, name='publish_course_item'),
    path('submissoes/<int:submission_id>/avaliar/', submission_review_view, name='submission_review'),
    path('cursos/<int:course_id>/solicitar-matricula/', request_enrollment_view, name='request_enrollment'),
    path('matriculas/<int:enrollment_id>/<str:decision>/', enrollment_decision_view, name='enrollment_decision'),
    path('login/', login_view, name='login'),
    path('users/create/', create_user_view, name='create_user'),
    path('logout/', logout_view, name='logout'),
]
