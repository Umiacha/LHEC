from django.urls import path

from views import students, study_materials


urlpatterns = [
    path('', students, name='students'),
    path('study_materials/', study_materials, name='study_materials'),
]