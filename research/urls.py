from django.urls import path

from . import views

app_name = 'research'

urlpatterns = [
    path('science/', views.science, name='science'),
    path('science/diplomas/files/<path:file_name>', views.download_diploma, name='download_diploma'),
    path('science/dissertations/files/<path:file_name>', views.download_dissertation, name='download_dissertation'),
    path('science/projects/', views.projects, name='projects'),
    path('science/projects/<slug:slug>/', views.project_detail, name='project_detail'),
    path('science/directions/<slug:slug>/', views.direction_detail, name='direction_detail'),
]
