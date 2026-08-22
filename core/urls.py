from django.urls import path

from core import views


app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),
    path('about/', views.about, name='about'),
    path('about/history', views.history, name='history'),
    path('people/', views.people, name='people'),
    path('science/', views.science, name='science'),
    path('science/projects/', views.projects, name='projects'),
    path('science/publications/', views.publications, name='publications'),
    path('students/', views.students, name='students'),
    path('students/materials/', views.study_materials, name='materials'),
    path('students/theses/', views.theses, name='theses'),
    path('news/', views.news, name='news'),
    path('gallery/', views.gallery, name='gallery'),
    path('contacts', views.contacts, name='contacts'),
]