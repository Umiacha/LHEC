from django.urls import path

from . import views

app_name = 'publications'

urlpatterns = [
    path('science/publications/', views.publications, name='publications',),
    path('science/publications/<int:pk>', views.publication, name='publication',),
]