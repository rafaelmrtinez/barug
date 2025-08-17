from django.urls import path
from . import api_views

urlpatterns = [
    path('register/', api_views.ResidentRegisterAPIView.as_view(), name='api-resident-register'),
    path('profile/', api_views.ResidentProfileAPIView.as_view(), name='api-resident-profile'),
    path('family-membership/', api_views.FamilyMembership.as_view(), name='api-family-membership'),
    path('households/search/', api_views.HouseholdMembershipSearch.as_view(), name='api-household-membership-search'),
    # path('profile/<int:pk>/', api_views.ResidentProfileAPIView.as_view(), name='api-resident-profile'),
]
