from django.urls import path

from . import views

app_name = 'publications'

urlpatterns = [
    path('science/publications/files/<path:file_name>', views.download_file, name='download_file'),
    path('science/publications/', views.publications, name='publications',),
    path('science/publications/<int:pk>/', views.publication, name='publication',),
]
