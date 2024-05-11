from django.urls import path
from . import views

app_name = 'users'
urlpatterns = [
    path('sign_up/', views.process_sign_up, name='sign_up'),
    path('sign_in/', views.process_sign_in, name='sign_in'),
    path('logout/', views.process_logout, name='logout'),
    path('change_password/', views.process_change_password, name='change_password')
]