from django.urls import path
from django.views.generic import RedirectView

from core import views


app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),
    path('about/', RedirectView.as_view(pattern_name='core:home', permanent=True)),
    path('about/history/', views.history, name='history'),
    path('news/', views.news, name='news'),
    path('gallery/', views.gallery, name='gallery'),
    path('contacts/', views.contacts, name='contacts'),
]