from django.urls import path
from . import api_views

urlpatterns = [
    path('register/', api_views.ResidentRegisterAPIView.as_view(), name='api-resident-register'),
    path('register-bhw/', api_views.ResidentRegisterBHWAPIView.as_view(), name='api-resident-register-bhw'),
    path('profile/', api_views.ResidentProfileAPIView.as_view(), name='api-resident-profile'),
    path('verify/', api_views.PersonVerificationRequestAPIView.as_view(), name='api-resident-verify'),
    path('family-membership/', api_views.FamilyMembership.as_view(), name='api-family-membership'),
    path('households/search/', api_views.HouseholdMembershipSearch.as_view(), name='api-household-membership-search'),
    path('fetch/families/', api_views.FamilyUnitSelection.as_view(), name='api-family-unit-selection'),
    # path('profile/<int:pk>/', api_views.ResidentProfileAPIView.as_view(), name='api-resident-profile'),
]

