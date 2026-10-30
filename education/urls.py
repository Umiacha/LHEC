from django.urls import path

from . import views


app_name = 'education'

urlpatterns = [
    path('students/study_materials/courses/<slug:slug>/', views.lecture_course_detail, name='lecture_course_detail'),
    path('lectures/preview/<path:file_name>/', views.view_lecture_file, name='view_lecture_file'),
    path('lectures/files/<path:file_name>/', views.download_lecture_file, name='download_lecture_file'),
    path('students/', views.students, name='students',),
    path('students/study_materials/', views.study_materials, name='study_materials',),
    path('students/theses/', views.theses, name='theses'),
    path('materials/<int:pk>/download/', views.download_material, name='download_material',),
]
