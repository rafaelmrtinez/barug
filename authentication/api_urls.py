from django.urls import path
from authentication.api_views import * # ✅ Check if this import exists and works

urlpatterns = [
    path('login/', ResidentLoginView.as_view(), name='resident-login'),
    path('email-confirmed/', EmailConfirmedAPIView.as_view(), name='email-confirmed'),
    path('resend-verification/', ResendVerificationEmailAPIView.as_view(), name='resend-verification'),   
    path("forgot-password/", ForgotPasswordAPIView.as_view(), name="forgot_password_api"),
    path("new-password/", ResetPasswordAPIView.as_view(), name="reset_password_api"), 

]