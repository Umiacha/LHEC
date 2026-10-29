from django.urls import path

from . import views

app_name = 'research'

urlpatterns = [
    path('science/directions/<slug:slug>/', views.direction_detail, name='direction_detail'),
]
