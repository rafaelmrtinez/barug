from django.urls import path
from . import api_views

urlpatterns = [
    path('register/', api_views.ResidentRegisterAPIView.as_view(), name='api-resident-register'),
    path('register-bhw/', api_views.ResidentRegisterBHWAPIView.as_view(), name='api-resident-register-bhw'),
    path('profile/', api_views.ResidentProfileAPIView.as_view(), name='api-resident-profile'),
    path('verify/', api_views.PersonVerificationRequestAPIView.as_view(), name='api-resident-verify'),
    # path('profile/<int:pk>/', api_views.ResidentProfileAPIView.as_view(), name='api-resident-profile'),
]

