# authentication/api_urls.py
from django.urls import path
from authentication.api_views import (
    ResidentLoginView,
    EmailConfirmedAPIView,
    ResendVerificationEmailAPIView,
    ForgotPasswordAPIView,
    ResetPasswordAPIView,
    BHWFieldVisitLoginAPIView,
    TokenRefreshAPIView,   # NEW
    LogoutAPIView,         # NEW
    CSRFTokenAPIView,      # NEW
)

app_name = "auth_api"

urlpatterns = [
    # Auth (residents)
    path("login/", ResidentLoginView.as_view(), name="resident-login"),
    path("refresh/", TokenRefreshAPIView.as_view(), name="token-refresh"),   # NEW
    path("logout/", LogoutAPIView.as_view(), name="logout"),                 # NEW
    path("csrf/", CSRFTokenAPIView.as_view(), name="csrf"),                  # NEW (GET only)

    # Email verification
    path("email-confirmed/", EmailConfirmedAPIView.as_view(), name="email-confirmed"),
    path("resend-verification/", ResendVerificationEmailAPIView.as_view(), name="resend-verification"),

    # Password reset
    path("forgot-password/", ForgotPasswordAPIView.as_view(), name="forgot_password_api"),
    path("new-password/", ResetPasswordAPIView.as_view(), name="reset_password_api"),

    # BHW login
    path("bhw-field-login/", BHWFieldVisitLoginAPIView.as_view(), name="bhw-field-login"),
]
