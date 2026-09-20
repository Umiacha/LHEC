from django.urls import path

from .views import UserLoginView, UserLogoutView, people, employe_card


app_name = 'users'

urlpatterns = [
    path('account/login/', UserLoginView.as_view(), name='login'),
    path('account/logout/', UserLogoutView.as_view(), name='logout'),
    path('people/', people, name='people'),
    path('people/<int:pk>', employe_card, name='employe_card')
]