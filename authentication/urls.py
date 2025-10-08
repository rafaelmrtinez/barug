from django.urls import path
from . import views

app_name = "authentication"

urlpatterns = [
    path("", views.login, name="login"),
    path("login/", views.login, name="login_alt"),
    path("logout/", views.logout, name="logout"),
    path("forgot-password/", views.forgot_password, name="forgot_password"),
    path("new-password/", views.new_password, name="new_password"),
    path("email-sent/", views.email_sent, name="email_sent"),
    path("email-confirmed/", views.email_confirmed, name="email_confirmed"),

    # New unauthorized endpoint
    path("unauthorized/", views.unauthorized, name="unauthorized"),
]

# (Optional) In your project root urls.py you can also set:
# handler403 = "authentication.views.unauthorized"
