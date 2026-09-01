from django.urls import path

from . import views


app_name = 'education'

urlpatterns = [
    path('students/', views.students, name='students',),
    path('students/study_materials/', views.study_materials, name='study_materials',),
    path('students/theses/', views.theses, name='theses'),
    path('materials/<int:pk>/download/', views.download_material, name='download_material',),
]