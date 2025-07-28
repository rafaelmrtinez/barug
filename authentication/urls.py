from django.urls import path
from . import views

app_name = 'authentication'

urlpatterns = [
    path("", views.login, name="login"),
    path("forgot_password/", views.forgot_password, name="forgot_password"),
    path("forgot_password/new_password/", views.new_password, name="new_password"),
    path("email_sent/", views.email_sent, name="email_sent"),
    path("email_confirmed/", views.email_confirmed, name="email_confirmed"),
    path("temporary_password/", views.temporary_password, name="temporary_pass"),
]