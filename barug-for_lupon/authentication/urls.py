from django.urls import path
from . import views
from .announcement_views import in_app_announcements

app_name = "authentication"

urlpatterns = [
    path("", views.login, name="login"),
    path("login/", views.login, name="login_alt"),
    path("logout/", views.logout, name="logout"),
    path("forgot-password/", views.forgot_password, name="forgot_password"),
    path("new-password/", views.new_password, name="new_password"),
    path("email-sent/", views.email_sent, name="email_sent"),
    path("email-confirmed/", views.email_confirmed, name="email_confirmed"),
    path("select-role/", views.select_role, name="select_role"),
    path("switch-role/", views.switch_role, name="switch_role"),

    # New unauthorized endpoint
    path("unauthorized/", views.unauthorized, name="unauthorized"),
    
    # Account settings
    path("account-settings/", views.account_settings, name="account_settings"),
    
    # In-app announcements
    path("announcements/", in_app_announcements, name="in_app_announcements"),
    
    # Debug endpoint (TEMPORARY - remove in production)
    path("debug-login-log/", views.debug_login_log, name="debug_login_log"),
]

# (Optional) In your project root urls.py you can also set:
# handler403 = "authentication.views.unauthorized"
